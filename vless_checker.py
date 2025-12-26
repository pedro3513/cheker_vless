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

# --- КОНФИГУРАЦИЯ ---
XRAY_BIN = "./xray"
INPUT_FILE = "input.txt"
OUTPUT_FILE = "output.txt"
CHECK_URL = "http://ip-api.com/json/?fields=status,countryCode,query"
TIMEOUT = 5          
MAX_WORKERS = 15     
BASE_NAME = "VLESS_Auto"

def setup_xray():
    """Скачивает ядро Xray для Linux (в среду GitHub Actions)"""
    if not os.path.exists("xray"):
        print("📥 Загрузка Xray core...")
        url = "https://github.com/XTLS/Xray-core/releases/latest/download/Xray-linux-64.zip"
        r = requests.get(url)
        with open("xray.zip", "wb") as f: f.write(r.content)
        with zipfile.ZipFile("xray.zip", 'r') as zip_ref: zip_ref.extractall(".")
        os.chmod("xray", 0o755)

def get_flag(code):
    if not code or len(code) != 2: return "🌐"
    return "".join(chr(127397 + ord(c)) for c in code.upper())

def decode_sub(url):
    """Качает подписку и вытаскивает vless ссылки"""
    headers = {'User-Agent': 'v2rayNG/1.8.5'}
    try:
        resp = requests.get(url, headers=headers, timeout=15)
        content = resp.text.strip().replace(' ', '').replace('\n', '').replace('\r', '')
        try:
            padded = content + "=" * (4 - len(content) % 4) if len(content) % 4 else content
            decoded = base64.b64decode(padded).decode('utf-8', errors='ignore')
        except:
            decoded = content
        return re.findall(r'vless://[^\s#|\n]+(?:#[^\s\n]+)?', decoded)
    except: return []

def parse_vless(link, port):
    """Генерирует JSON конфиг для проверки"""
    try:
        parsed = urlparse(link)
        params = parse_qs(parsed.query)
        return {
            "log": {"loglevel": "none"},
            "inbounds": [{"port": port, "protocol": "socks", "settings": {"udp": True}}],
            "outbounds": [{
                "protocol": "vless",
                "settings": {
                    "vnext": [{
                        "address": parsed.hostname,
                        "port": parsed.port or 443,
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
                        "shortId": params.get('sid', [''])[0],
                        "spiderX": params.get('spx', [''])[0]
                    }
                }
            }]
        }
    except: return None

def check_link(link):
    """Проверяет сервер и возвращает его с флагом страны"""
    # Ищем свободный порт
    with socket.socket() as s:
        s.bind(('', 0))
        p_num = s.getsockname()[1]
    
    config = parse_vless(link, p_num)
    if not config: return None
    
    c_file = f"temp_{p_num}.json"
    with open(c_file, 'w') as f: json.dump(config, f)
    
    try:
        proc = subprocess.Popen([XRAY_BIN, "run", "-c", c_file], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        time.sleep(2)
        res = None
        try:
            proxies = {'http': f'socks5h://127.0.0.1:{p_num}', 'https': f'socks5h://127.0.0.1:{p_num}'}
            r = requests.get(CHECK_URL, proxies=proxies, timeout=TIMEOUT)
            data = r.json()
            if data.get("status") == "success":
                flag = get_flag(data.get("countryCode"))
                res = f"{link.split('#')[0]}#{quote(flag + ' ' + BASE_NAME)}"
        except: pass
        proc.terminate()
        proc.wait()
        return res
    finally:
        if os.path.exists(c_file): os.remove(c_file)

def main():
    setup_xray()
    if not os.path.exists(INPUT_FILE): return
    with open(INPUT_FILE, 'r') as f: urls = [l.strip() for l in f if l.strip()]
    
    all_links = []
    for u in urls:
        if u.startswith('http'): all_links.extend(decode_sub(u))
        else: all_links.append(u)
    
    all_links = list(dict.fromkeys(all_links))
    print(f"📡 Собрано {len(all_links)} ссылок. Проверяю...")
    
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as ex:
        results = list(ex.map(check_link, all_links))
    
    valid = [r for r in results if r]
    with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
        f.write("\n".join(valid))
    print(f"✅ Готово! Рабочих серверов: {len(valid)}")

if __name__ == "__main__":
    main()
