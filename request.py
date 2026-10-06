# pip install curl_cffi
from curl_cffi import requests

url = "https://api.mangamello.com/v1/mangas/22979?relations=genres,chapters&rate=false"

headers = {
    "Accept": "application/json",
    "Accept-Encoding": "gzip, deflate",
    "Accept-Language": "fr-FR,fr;q=0.9,en-US;q=0.8,en;q=0.7",
    "App-Version": "2.0.9",
    "Connection": "keep-alive",
    "Content-Type": "application/json",
    "Device-Langs": "fr",
    "Device-UUID": "afcba58d68d5ae11",
    "Host": "api.mangamello.com",
    "Origin": "https://localhost",
    "Referer": "https://localhost/",
    "Sec-Fetch-Dest": "empty",
    "Sec-Fetch-Mode": "cors",
    "Sec-Fetch-Site": "cross-site",
    "Time-Zone": "Europe/Paris",
    "User-Agent": "Mozilla/5.0 (Linux; Android 15; SM-A5560 Build/V417IR; wv) AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 Chrome/110.0.5481.154 Mobile Safari/537.36",
    "X-app-installer": "cm.aptoide.pt",
    "X-Requested-With": "com.wael.mangamello",
}

r = requests.get(url, headers=headers, impersonate="chrome110", timeout=30)

print("Status:", r.status_code)
print("Headers:", dict(r.headers))
try:
    print(r.json())
except Exception:
    print(r.text[:2000])