import subprocess
import json
import time
import requests
import os
import socket
import base64
import re
import zipfile
from urllib.parse import urlparse, parse_qs, quote
from concurrent.futures import ThreadPoolExecutor

# --- НАСТРОЙКИ ---
XRAY_BIN = "./xray"
INPUT_FILE = "input.txt"
OUTPUT_FILE = "output.txt"
CHECK_URL = "http://ip-api.com/json/?fields=status,countryCode,query"
TIMEOUT = 7 # Чуть увеличил таймаут для стабильности
MAX_WORKERS = 10 
BASE_NAME = "VLESS_AUTO"

def setup_xray():
    if not os.path.exists("xray"):
        print("📥 Загрузка Xray core...")
        url = "https://github.com/XTLS/Xray-core/releases/latest/download/Xray-linux-64.zip"
        r = requests.get(url)
        with open("xray.zip", "wb") as f: f.write(r.content)
        with zipfile.ZipFile("xray.zip", 'r') as zip_ref: zip_ref.extractall(".")
        os.chmod("xray", 0o755)
        print("✅ Xray установлен")

def decode_sub(url):
    headers = {'User-Agent': 'v2rayNG/1.8.5'}
    try:
        print(f"🌐 Качаю подписку: {url}")
        resp = requests.get(url, headers=headers, timeout=15)
        content = resp.text.strip().replace(' ', '')
        
        # Пытаемся понять, это Base64 или чистый текст
        if "vless://" not in content:
            print("📦 Похоже на Base64, декодирую...")
            try:
                padded = content + "=" * (4 - len(content) % 4) if len(content) % 4 else content
                decoded = base64.b64decode(padded).decode('utf-8', errors='ignore')
            except:
                decoded = content
        else:
            print("📄 Контент в открытом виде")
            decoded = content

        links = re.findall(r'vless://[^\s#|\n|"]+', decoded)
        print(f"🔎 Найдено ссылок в источнике: {len(links)}")
        return links
    except Exception as e:
        print(f"❌ Ошибка загрузки подписки: {e}")
        return []

def parse_vless(link, port):
    try:
        # Убираем имя из ссылки для парсинга параметров
        clean_link = link.split('#')[0]
        parsed = urlparse(clean_link)
        params = parse_qs(parsed.query)
        
        config = {
            "log": {"loglevel": "none"},
            "inbounds": [{"port": port, "protocol": "socks", "settings": {"udp": True}}],
            "outbounds": [{
                "protocol": "vless",
                "settings": {
                    "vnext": [{
                        "address": parsed.hostname,
                        "port": int(parsed.port) if parsed.port else 443,
                        "users": [{"id": parsed.username, "encryption": params.get('encryption', ['none'])[0], "flow": params.get('flow', [''])[0]}]
                    }]
                },
                "streamSettings": {
                    "network": params.get('type', ['tcp'])[0],
                    "security": params.get('security', ['none'])[0],
                    "tlsSettings": {"serverName": params.get('sni', [''])[0]},
                    "realitySettings": {
                        "serverName": params.get('sni', [''])[0],
                        "publicKey": params.get('pbk', [''])[0],
                        "shortId": params.get('sid', [''])[0]
                    }
                }
            }]
        }
        return config
    except: return None

def check_link(link):
    # Берем случайный свободный порт
    with socket.socket() as s:
        s.bind(('', 0))
        p_num = s.getsockname()[1]
    
    config = parse_vless(link, p_num)
    if not config: return None
    
    c_file = f"temp_{p_num}.json"
    with open(c_file, 'w') as f: json.dump(config, f)
    
    try:
        proc = subprocess.Popen([XRAY_BIN, "run", "-c", c_file], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        time.sleep(2.5) # Даем время на запуск
        
        res = None
        try:
            proxies = {'http': f'socks5h://127.0.0.1:{p_num}', 'https': f'socks5h://127.0.0.1:{p_num}'}
            r = requests.get(CHECK_URL, proxies=proxies, timeout=TIMEOUT)
            if r.status_code == 200:
                data = r.json()
                country = data.get("countryCode", "??")
                print(f"✅ Работает! [{country}]")
                res = f"{link.split('#')[0]}#{country}_{BASE_NAME}"
        except:
            pass
        
        proc.terminate()
        proc.wait()
        return res
    finally:
        if os.path.exists(c_file): os.remove(c_file)

def main():
    setup_xray()
    if not os.path.exists(INPUT_FILE):
        print(f"❌ {INPUT_FILE} не найден!")
        return
        
    with open(INPUT_FILE, 'r') as f:
        urls = [l.strip() for l in f if l.strip()]
    
    print(f"📖 Читаю {len(urls)} источников из {INPUT_FILE}")
    all_links = []
    for u in urls:
        all_links.extend(decode_sub(u))
    
    all_links = list(dict.fromkeys(all_links))
    print(f"🚀 Итого уникальных ссылок для проверки: {len(all_links)}")
    
    if not all_links:
        print("⚠ Нечего проверять. Выхожу.")
        return

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as ex:
        results = list(ex.map(check_link, all_links))
    
    valid = [r for r in results if r]
    
    with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
        f.write("\n".join(valid))
    
    print(f"🏁 Сохранено {len(valid)} рабочих конфигов в {OUTPUT_FILE}")

if __name__ == "__main__":
    main()
