from typing import Literal
import inspect
import io
import json
import logging
import os
import re
import subprocess
import tempfile
from contextlib import asynccontextmanager

import httpx
import numpy as np
import soundfile as sf
import torch
import yt_dlp
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse, StreamingResponse
from googletrans import Translator
from pydantic import BaseModel
from silero import silero_tts

logger = logging.getLogger(__name__)

load_dotenv()

# ─── Configuration ───────────────────────────────────────────────────────────

MODEL_PATH = os.path.expanduser("~/Models/Qwen3.8-9B-Q4_K_M.gguf")
LLAMA_SERVER_HOST = "127.0.0.1"
LLAMA_SERVER_PORT = 8081  # internal port for llama-server
SAMPLE_RATE = 48000

# ─── Global state ────────────────────────────────────────────────────────────

tts_model = None
llama_process = None
tts_models = {}


RUSSIAN_PPHRASE_SYSTEM_PROMPT = """\
You are a Russian language tutor for A1-level beginners.
When the user gives you a Russian word or phrase, do the following concisely:

1. **Translation**: Give the English meaning.
2. **Word-by-word breakdown**: List each word, its part of speech (noun, verb, adjective, etc.), and meaning.
3. **Verbs**: For each verb, state:
   - The infinitive (base form)
   - The root
   - The suffix/ending used and WHY (which conjugation, tense, person, number)
4. **Adjectives**: State gender/case agreement if relevant.

Keep answers SHORT, DIRECT, and CORRECT. Use simple A1-level explanations.
Do NOT write long paragraphs. Use bullet points.
"""


ENGLISH_PPHRASE_SYSTEM_PROMPT = """\
You are a ENGLISH language tutor for A1-level beginners.
When the user gives you a English word or phrase, do the following concisely:

1. **Translation**: Give the Russian meaning.
2. **Word-by-word breakdown**: List each word, its part of speech (noun, verb, adjective, etc.), and meaning.
3. **Verbs**: For each verb, state:
   - The infinitive (base form)
   - The root
   - The suffix/ending used and WHY (which conjugation, tense, person, number)
4. **Adjectives**: State gender/case agreement if relevant.

Keep answers SHORT, DIRECT, and CORRECT. Use simple A1-level explanations.
Do NOT write long paragraphs. Use bullet points.
"""


# ─── Lifespan: load TTS + start llama-server ─────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    global tts_model, llama_process, tts_models

    # Load Silero TTS
    print("⏳ Loading Silero TTS model...")
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    ru_model, _ = silero_tts(language="ru", speaker="v5_ru")
    ru_model.to(device)

    en_model, _ = silero_tts(language="en", speaker="v3_en")
    en_model.to(device)

    tts_models["ru"] = ru_model
    tts_models["en"] = en_model
    print(f"✅ Silero TTS loaded on {device}")

    # Start llama-server as a subprocess with GPU offload
    print("⏳ Starting llama-server...")
    llama_process = subprocess.Popen(
        [
            "llama-server",
            "-m", MODEL_PATH,
            "--host", LLAMA_SERVER_HOST,
            "--port", str(LLAMA_SERVER_PORT),
            "-ngl", "99",       # offload all layers to GPU
            "-c", "65536",       # context size
            "--no-warmup",
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
    )
    # Wait a bit for llama-server to be ready
    import time
    time.sleep(2)

    # Poll to check it started OK
    if llama_process.poll() is not None:
        stderr_out = llama_process.stderr.read().decode() if llama_process.stderr else ""
        print(f"❌ llama-server failed to start:\n{stderr_out}")
    else:
        print(f"✅ llama-server running on http://{LLAMA_SERVER_HOST}:{LLAMA_SERVER_PORT}")

    yield

    # Shutdown
    if llama_process and llama_process.poll() is None:
        print("🛑 Stopping llama-server...")
        llama_process.terminate()
        llama_process.wait(timeout=10)
    print("👋 Shutdown complete.")


# ─── App ─────────────────────────────────────────────────────────────────────

app = FastAPI(
    title="Russian Learning API",
    description="TTS, AI-powered Russian language analysis, and YouTube subtitle translation",
    lifespan=lifespan,
)


# ─── Request/Response models ────────────────────────────────────────────────

class TTSRequest(BaseModel):
    text: str
    speed: float = 1.0
    speaker: str = "xenia"
    language: str

class Message(BaseModel):
    role: Literal["user", "assistant"]
    content: str


class ModelRequest(BaseModel):
    text: str
    learning_language: str
    history: list[Message] = []

class ModelResponse(BaseModel):
    response: str

class TranslateRequest(BaseModel):
    """Request model for the translate endpoint."""
    url: str
    language: str


# ─── Health check ────────────────────────────────────────────────────────────

@app.get("/")
async def root():
    """Health check endpoint."""
    return {"status": "ok", "service": "Russian Learning & Translation API"}


# ─── Endpoint: /russian-tts ─────────────────────────────────────────────────

@app.post("/russian-tts")
async def russian_tts(req: TTSRequest):
    """
    Convert Russian text to speech using Silero TTS.
    Returns a WAV audio file.
    """
    if not req.text.strip():
        raise HTTPException(status_code=400, detail="Text cannot be empty")

    if not 0.5 <= req.speed <= 2.0:
        raise HTTPException(status_code=400, detail="Speed must be between 0.5 and 2.0")

    try:
        model = tts_models[req.language]


        audio = model.apply_tts(
            text=req.text.strip(),
            speaker=req.speaker,
            sample_rate=SAMPLE_RATE,
        )
        audio_np = audio.cpu().numpy()

        # Apply speed change
        if req.speed != 1.0:
            indices = np.arange(0, len(audio_np), req.speed)
            indices = indices[indices < len(audio_np)].astype(int)
            audio_np = audio_np[indices]

        # Write to WAV buffer
        buf = io.BytesIO()
        sf.write(buf, audio_np, SAMPLE_RATE, format="WAV")
        buf.seek(0)

        return StreamingResponse(
            buf,
            media_type="audio/wav",
            headers={"Content-Disposition": "attachment; filename=tts_output.wav"},
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"TTS generation failed: {e}")


# ─── Endpoint: /model (SSE Streaming) ───────────────────────────────────────

@app.post("/model")
async def model_analyze(req: ModelRequest):
    """
    Analyze a Russian word or phrase using the local Qwen 9B model.
    Streams tokens via Server-Sent Events (SSE) for instant feedback.
    Supports conversation history.
    """

    if not req.text.strip():
        raise HTTPException(status_code=400, detail="Text cannot be empty")

    if req.learning_language == "Russian":
        messages = [
            {"role": "system", "content": RUSSIAN_PPHRASE_SYSTEM_PROMPT},
        ]
    else:
        messages = [
            {"role": "system", "content": ENGLISH_PPHRASE_SYSTEM_PROMPT},
        ]

    # Add previous conversation
    messages.extend(
        {
            "role": message.role,
            "content": message.content,
        }
        for message in req.history
    )

    # Add current user message
    messages.append(
        {
            "role": "user",
            "content": req.text.strip(),
        }
    )

    async def stream_tokens():
        """Generator that streams tokens from llama-server, stripping <think> blocks."""
        inside_think = False
        think_buffer = ""

        try:
            async with httpx.AsyncClient(timeout=120.0) as client:
                async with client.stream(
                    "POST",
                    f"http://{LLAMA_SERVER_HOST}:{LLAMA_SERVER_PORT}/v1/chat/completions",
                    json={
                        "messages": messages,
                        "temperature": 0.4,
                        "stream": True,
                    },
                ) as resp:
                    resp.raise_for_status()

                    async for line in resp.aiter_lines():
                        # SSE format: "data: {...}"
                        if not line.startswith("data: "):
                            continue

                        payload = line[6:]  # strip "data: "

                        if payload.strip() == "[DONE]":
                            yield "data: [DONE]\n\n"
                            return

                        try:
                            chunk = json.loads(payload)
                        except json.JSONDecodeError:
                            continue

                        delta = chunk.get("choices", [{}])[0].get("delta", {})
                        token = delta.get("content", "")

                        if not token:
                            continue

                        # Filter out <think>...</think> blocks from Qwen3
                        think_buffer += token

                        while think_buffer:
                            if inside_think:
                                # Look for closing </think>
                                end_idx = think_buffer.find("</think>")
                                if end_idx != -1:
                                    # Found end — discard everything up to and including </think>
                                    think_buffer = think_buffer[end_idx + 8:]
                                    inside_think = False
                                else:
                                    # Still inside think — might be partial tag, hold buffer
                                    # Only keep last 8 chars in case </think> is split across chunks
                                    if len(think_buffer) > 8:
                                        think_buffer = think_buffer[-8:]
                                    break
                            else:
                                # Look for opening <think>
                                start_idx = think_buffer.find("<think>")
                                if start_idx != -1:
                                    # Emit everything before <think>
                                    before = think_buffer[:start_idx]
                                    if before:
                                        yield f"data: {json.dumps({'token': before})}\n\n"
                                    think_buffer = think_buffer[start_idx + 7:]
                                    inside_think = True
                                elif "<" in think_buffer:
                                    # Might be a partial <think> tag — emit safe part, hold the rest
                                    safe_idx = think_buffer.rfind("<")
                                    safe = think_buffer[:safe_idx]
                                    if safe:
                                        yield f"data: {json.dumps({'token': safe})}\n\n"
                                    think_buffer = think_buffer[safe_idx:]
                                    break
                                else:
                                    # No tags — emit everything
                                    yield f"data: {json.dumps({'token': think_buffer})}\n\n"
                                    think_buffer = ""

                    # Flush any remaining buffer
                    if think_buffer and not inside_think:
                        yield f"data: {json.dumps({'token': think_buffer})}\n\n"

                    yield "data: [DONE]\n\n"

        except httpx.ConnectError:
            yield f"data: {json.dumps({'error': 'LLM server is not ready yet. Please wait and try again.'})}\n\n"
        except Exception as e:
            yield f"data: {json.dumps({'error': str(e)})}\n\n"

    return StreamingResponse(
        stream_tokens(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


# ─── Endpoint: /model (SSE Streaming) ───────────────────────────────────────

@app.post("/model/video-explanation")
async def model_video_explanation(req: ModelRequest):
    """
    Analyze a Russian word or phrase using the local Qwen 9B model.
    Streams tokens via Server-Sent Events (SSE) for instant feedback.
    Supports conversation history.
    """

    if not req.text.strip():
        raise HTTPException(status_code=400, detail="Text cannot be empty")

    if req.learning_language == "Russian":
        messages = [
            {"role": "system", "content": """
        You are an expert russian teacher for begginers.
        You are an expert at explaining in simple words
        You can ask 2 questions at the end in russian + english (Like : Как тебя зовут? (Kak tebya zovut?)“What’s your name?”)
        The questions should be related to the video
        The questions should be easy to answer
        

        The user can answer you about the questions, so you should be able to understand the answer and respond accordingly and rate him.

        Keep the conversation alive and try to make him speak more and learn more.

        IMPORTANT :
        - you must explain the video and answer in English.
        """},
        ]
    else:
        messages = [
            {"role": "system", "content": """
You are an expert English teacher for A1 beginners.

Help the learner understand the video, learn useful English, and speak more.

Rules:
* Talk and explain and answer in Russian.
* Use simple A1 English and short answers.
* Explain vocabulary, grammar, and corrections in Russian.
* Give Russian meanings for new English words.
* Encourage the learner to answer in English.
* Understand imperfect beginner English.
* Correct important mistakes gently with a short explanation.
* Praise correct answers briefly.
* Keep the conversation natural and engaging.
* Ask 1–2 easy questions related to the video.
* For each question, give English + simple pronunciation + Russian meaning.
* Ask follow-up questions when appropriate.
* Focus on communication, vocabulary, and basic grammar, not advanced explanations.
* Never overwhelm the learner with long paragraphs.
* When evaluating an answer, briefly say what was good, correct important mistakes, and give a 1–10 score when appropriate.
        """},
        ]

    # Add previous conversation
    messages.extend(
        {
            "role": message.role,
            "content": message.content,
        }
        for message in req.history
    )

    # Add current user message
    messages.append(
        {
            "role": "user",
            "content": req.text.strip(),
        }
    )

    async def stream_tokens():
        """Generator that streams tokens from llama-server, stripping <think> blocks."""
        inside_think = False
        think_buffer = ""

        try:
            async with httpx.AsyncClient(timeout=120.0) as client:
                async with client.stream(
                    "POST",
                    f"http://{LLAMA_SERVER_HOST}:{LLAMA_SERVER_PORT}/v1/chat/completions",
                    json={
                        "messages": messages,
                        "temperature": 0.4,
                        "stream": True,
                    },
                ) as resp:
                    resp.raise_for_status()

                    async for line in resp.aiter_lines():
                        # SSE format: "data: {...}"
                        if not line.startswith("data: "):
                            continue

                        payload = line[6:]  # strip "data: "

                        if payload.strip() == "[DONE]":
                            yield "data: [DONE]\n\n"
                            return

                        try:
                            chunk = json.loads(payload)
                        except json.JSONDecodeError:
                            continue

                        delta = chunk.get("choices", [{}])[0].get("delta", {})
                        token = delta.get("content", "")

                        if not token:
                            continue

                        # Filter out <think>...</think> blocks from Qwen3
                        think_buffer += token

                        while think_buffer:
                            if inside_think:
                                # Look for closing </think>
                                end_idx = think_buffer.find("</think>")
                                if end_idx != -1:
                                    # Found end — discard everything up to and including </think>
                                    think_buffer = think_buffer[end_idx + 8:]
                                    inside_think = False
                                else:
                                    # Still inside think — might be partial tag, hold buffer
                                    # Only keep last 8 chars in case </think> is split across chunks
                                    if len(think_buffer) > 8:
                                        think_buffer = think_buffer[-8:]
                                    break
                            else:
                                # Look for opening <think>
                                start_idx = think_buffer.find("<think>")
                                if start_idx != -1:
                                    # Emit everything before <think>
                                    before = think_buffer[:start_idx]
                                    if before:
                                        yield f"data: {json.dumps({'token': before})}\n\n"
                                    think_buffer = think_buffer[start_idx + 7:]
                                    inside_think = True
                                elif "<" in think_buffer:
                                    # Might be a partial <think> tag — emit safe part, hold the rest
                                    safe_idx = think_buffer.rfind("<")
                                    safe = think_buffer[:safe_idx]
                                    if safe:
                                        yield f"data: {json.dumps({'token': safe})}\n\n"
                                    think_buffer = think_buffer[safe_idx:]
                                    break
                                else:
                                    # No tags — emit everything
                                    yield f"data: {json.dumps({'token': think_buffer})}\n\n"
                                    think_buffer = ""

                    # Flush any remaining buffer
                    if think_buffer and not inside_think:
                        yield f"data: {json.dumps({'token': think_buffer})}\n\n"

                    yield "data: [DONE]\n\n"

        except httpx.ConnectError:
            yield f"data: {json.dumps({'error': 'LLM server is not ready yet. Please wait and try again.'})}\n\n"
        except Exception as e:
            yield f"data: {json.dumps({'error': str(e)})}\n\n"

    return StreamingResponse(
        stream_tokens(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )



# ─── Subtitle helper functions ──────────────────────────────────────────────

def _fetch_russian_subtitles(video_url: str, language: str = "ru") -> list[dict]:
    """
    Fetch Russian subtitles from a YouTube video using yt-dlp.

    Uses yt-dlp to download subtitles in json3 format (structured with
    timestamps), then parses them into a list of segments.

    Args:
        video_url: The YouTube video URL.

    Returns:
        List of dicts with 'start', 'end', and 'text' keys.

    Raises:
        HTTPException: If no Russian subtitles are found or download fails.
    """
    cookie_path = os.path.join(
        os.path.dirname(os.path.abspath(__file__)),
        "cookies.txt",
    )

    print("COOKIE EXISTS:", os.path.exists(cookie_path))
    print("COOKIE SIZE:", os.path.getsize(cookie_path) if os.path.exists(cookie_path) else 0)

    proxy = None
    webshare_username = os.environ.get("WEBSHARE_USERNAME")
    webshare_password = os.environ.get("WEBSHARE_PASSWORD")
    if webshare_username and webshare_password:
        proxy = f"http://{webshare_username}:{webshare_password}@p.webshare.io:80"

    with tempfile.TemporaryDirectory() as tmpdir:
        ydl_opts = {
            "skip_download": True,
            "writesubtitles": True,
            "writeautomaticsub": True,
            "subtitleslangs": [language],
            "subtitlesformat": "json3",

            "remote_components": "ejs:github",

            "outtmpl": os.path.join(tmpdir, "%(id)s.%(ext)s"),

            "quiet": True,
            "no_warnings": True,
            "socket_timeout": 30,

            "cookiefile": os.path.join(
                os.path.dirname(os.path.abspath(__file__)),
                "cookies.txt",
            ),
        }
        if proxy:
            ydl_opts["proxy"] = proxy

        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.download([video_url])
        except yt_dlp.utils.DownloadError as e:
            err_msg = str(e)
            if "429" in err_msg or "too many" in err_msg.lower():
                raise HTTPException(
                    status_code=429,
                    detail="YouTube is rate-limiting requests. Please try again later.",
                )
            if "Private video" in err_msg or "Sign in" in err_msg:
                raise HTTPException(
                    status_code=403,
                    detail="This video is private or requires sign-in.",
                )
            raise HTTPException(
                status_code=500,
                detail=f"Failed to fetch video info: {err_msg}",
            )

        # Find the downloaded subtitle file
        sub_file = None
        for fname in os.listdir(tmpdir):
            if fname.endswith(f".{language}.json3"):
                sub_file = os.path.join(tmpdir, fname)
                break

        if not sub_file:
            raise HTTPException(
                status_code=404,
                detail="No " + language + " subtitles found for this video. "
                "The video may have no captions or no "+ language + " track.",
            )

        with open(sub_file, "r", encoding="utf-8") as f:
            data = json.load(f)

    # Parse json3 format into segments
    segments = []
    for event in data.get("events", []):
        if "segs" not in event:
            continue
        text = "".join(seg.get("utf8", "") for seg in event["segs"]).strip()
        if not text or text == "\n":
            continue
        start_ms = event.get("tStartMs", 0)
        duration_ms = event.get("dDurationMs", 0)
        segments.append(
            {
                "start": round(start_ms / 1000, 2),
                "end": round((start_ms + duration_ms) / 1000, 2),
                "text": text,
            }
        )

    if not segments:
        raise HTTPException(
            status_code=404,
            detail="Subtitles were found but contained no text content.",
        )

    return segments


# ─── Endpoint: /translate ───────────────────────────────────────────────────

@app.post("/translate")
async def translate_subtitles(request: TranslateRequest):
    """
    Extract subtitles from a YouTube video and translate them to English.

    Args:
        request: The request body containing the YouTube URL.

    Returns:
        JSON list of subtitle segments with start, end, text, and translation.

    Raises:
        HTTPException: If the video has no subtitles or translation fails.
    """
    try:
        # Fetch Russian subtitles using yt-dlp
        raw_segments = _fetch_russian_subtitles(request.url, request.language)

        # Translate segments
        translated = []
        translator = Translator()

        # Attempt batch translation first for performance
        texts_to_translate = [s["text"] for s in raw_segments]
        translations = []
        try:
            print(request.language)
            batch_res = translator.translate(texts_to_translate, src=request.language , dest="en" if request.language == "ru" else "ru")
            if inspect.isawaitable(batch_res):
                batch_res = await batch_res
            translations = [r.text for r in batch_res]
        except Exception:
            translations = []

        if len(translations) == len(raw_segments):
            for seg, trans_text in zip(raw_segments, translations):
                translated.append(
                    {
                        "start": seg["start"],
                        "end": seg["end"],
                        "text": seg["text"],
                        "translation": trans_text,
                    }
                )
        else:
            # Fallback: translate segment by segment
            for seg in raw_segments:
                text = seg["text"]
                try:
                    res = translator.translate(text, src=request.language , dest="en" if request.language == "ru" else "ru")
                    if inspect.isawaitable(res):
                        res = await res
                    trans_text = res.text
                except Exception:
                    trans_text = text

                translated.append(
                    {
                        "start": seg["start"],
                        "end": seg["end"],
                        "text": text,
                        "translation": trans_text,
                    }
                )

        return JSONResponse(
            status_code=200,
            content={"subtitles": translated},
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ─── Run ─────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
