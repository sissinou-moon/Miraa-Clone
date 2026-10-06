import requests

# 3 | 

API = (
    "https://datasets-server.huggingface.co/rows"
    "?dataset=NCSpeech/YO-CPT-ru"
    "&config=default"
    "&split=train"
    "&offset=63"
    "&length=1"
)

data = requests.get(API)
data.raise_for_status()

row = data.json()["rows"][0]["row"]

print("Text:", row["text"])
print("Speaker:", row["global_spk_id"])
print("Description:", row["spk_desc"])

audio_url = row["audio"][0]["src"]

response = requests.get(audio_url)
response.raise_for_status()

with open("voice.wav", "wb") as f:
    f.write(response.content)

print("Saved: voice.wav")