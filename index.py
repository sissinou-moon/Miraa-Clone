import subprocess
from pathlib import Path
from telegram import Update
from telegram.ext import Application, MessageHandler, ContextTypes, filters

BOT_TOKEN = "8688866136:AAHaXbudJ5g0AaKoUgVpX0ZgWEiotLapEl8"

MODEL = "ggml-org/Qwen3-TTS-12Hz-1.7B-Base-GGUF:Q4_K_M"

SPEAKER = "voice.wav" 

def generate_tts(text: str, output: str):
    subprocess.run(
        [
            "llama-tts",
            "-hf", MODEL,
            "-p", text,
            "--tts-lang", "ru",
            "--output", output,
        ],
        check=True,
    )


def convert_to_ogg(wav: str, ogg: str, speed: float):
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-i", wav,
            "-filter:a", f"atempo={speed}",
            "-c:a", "libopus",
            "-b:a", "64k",
            ogg,
        ],
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


async def handle_message(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    if not update.message or not update.message.text:
        return

    message = update.message.text

    if not message.lower().startswith("tts:"):
        return
    
    content = message[4:].strip()
    
    speed = 1.0
    
    if " | speed:" in content.lower():
        text, speed_part = content.rsplit(" | speed:", 1)
    
        text = text.strip()
    
        try:
            speed = float(speed_part.strip())
        except ValueError:
            await update.message.reply_text(
                "❌ Invalid speed. Example: | speed: 0.7"
            )
            return
    else:
        text = content
    
    if not text:
        return
    
    if not 0.5 <= speed <= 2.0:
        await update.message.reply_text(
            "❌ Speed must be between 0.5 and 2.0."
        )
        return

    await update.message.reply_text(
        f"🎙️ Generating... (speed: {speed})"
    )

    wav = "tts_output.wav"
    ogg = "tts_output.ogg"

    try:
        generate_tts(text, wav)
        convert_to_ogg(wav, ogg, speed)

        with open(ogg, "rb") as voice:
            await update.message.reply_voice(
                voice=voice,
                reply_to_message_id=update.message.id,
            )

    except Exception as e:
        await update.message.reply_text(f"❌ Error: {e}")

    finally:
        Path(wav).unlink(missing_ok=True)
        Path(ogg).unlink(missing_ok=True)


def main():
    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(
        MessageHandler(
            filters.TEXT & ~filters.COMMAND,
            handle_message,
        )
    )

    print("🎙️ TTS Telegram bot running...")
    app.run_polling()


if __name__ == "__main__":
    main()
