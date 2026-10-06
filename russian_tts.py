import torch
import sounddevice as sd
from silero import silero_tts

device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

print("Loading Silero...")
model, example_text = silero_tts(
    language="ru",
    speaker="v5_ru",
)

model.to(device)

text = """
живу в городе.
"""

speed = 1.0  # 1.0 = normal, 1.2 = 20% faster, 0.8 = slower

audio = model.apply_tts(
    text=text,
    speaker="xenia",
    sample_rate=48000,
)

audio = audio.cpu().numpy()

# Change playback speed
if speed != 1.0:
    import numpy as np

    indices = np.arange(0, len(audio), speed)
    indices = indices[indices < len(audio)].astype(int)
    audio = audio[indices]

print(f"Speaking at {speed}x...")

sd.play(audio, 48000)
sd.wait()

print("Done.")
