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
# Используем более стабильный URL для проверки
CHECK_URL = "http://www.google.com/generate_204"
TIMEOUT = 10         
MAX_WORKERS = 8      # Уменьшил количество потоков, чтобы не забивать канал GitHub
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
        print(f"🌐 Источник: {url}")
        resp = requests.get(url, headers=headers, timeout=15)
        content = resp.text.strip().replace(' ', '')
        if "vless://" not in content:
            try:
                padded = content + "=" * (4 - len(content) % 4) if len(content) % 4 else content
                decoded = base64.b64decode(padded).decode('utf-8', errors='ignore')
            except: decoded = content
        else: decoded = content
        links = re.findall(r'vless://[^\s#|\n|"]+', decoded)
        return links
    except: return []

def parse_vless(link, port):
    try:
        clean_link = link.split('#')[0]
        parsed = urlparse(clean_link)
        params = {k: v[0] for k, v in parse_qs(parsed.query).items()}
        
        config = {
            "log": {"loglevel": "none"},
            "inbounds": [{"port": port, "protocol": "socks", "settings": {"udp": True}, "sniffing": {"enabled": True, "destOverride": ["http", "tls"]}}],
            "outbounds": [{
                "protocol": "vless",
                "settings": {
                    "vnext": [{
                        "address": parsed.hostname,
                        "port": int(parsed.port) if parsed.port else 443,
                        "users": [{"id": parsed.username, "encryption": params.get('encryption', 'none'), "flow": params.get('flow', '')}]
                    }]
                },
                "streamSettings": {
                    "network": params.get('type', 'tcp'),
                    "security": params.get('security', 'none'),
                    "tlsSettings": {"serverName": params.get('sni', '')},
                    "realitySettings": {
                        "serverName": params.get('sni', ''),
                        "publicKey": params.get('pbk', ''),
                        "shortId": params.get('sid', ''),
                        "spiderX": params.get('spx', '')
                    },
                    "wsSettings": {"path": params.get('path', '/')},
                    "grpcSettings": {"serviceName": params.get('serviceName', '')}
                }
            }]
        }
        return config
    except: return None

def check_link(link):
    # Поиск порта
    with socket.socket() as s:
        s.bind(('', 0))
        p_num = s.getsockname()[1]
    
    config = parse_vless(link, p_num)
    if not config: return None
    
    c_file = f"temp_{p_num}.json"
    with open(c_file, 'w') as f: json.dump(config, f)
    
    res = None
    try:
        proc = subprocess.Popen([XRAY_BIN, "run", "-c", c_file], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        time.sleep(3) # Увеличено время ожидания
        
        try:
            proxies = {'http': f'socks5h://127.0.0.1:{p_num}', 'https': f'socks5h://127.0.0.1:{p_num}'}
            r = requests.get(CHECK_URL, proxies=proxies, timeout=TIMEOUT)
            if r.status_code == 204 or r.status_code == 200:
                print(f"✅ OK: {link[:30]}...")
                res = f"{link.split('#')[0]}#Checked_{int(time.time())}"
        except: pass
        
        proc.terminate()
        proc.wait()
    finally:
        if os.path.exists(c_file): os.remove(c_file)
    return res

def main():
    setup_xray()
    if not os.path.exists(INPUT_FILE): return
    with open(INPUT_FILE, 'r') as f: urls = [l.strip() for l in f if l.strip()]
    
    all_links = []
    for u in urls: all_links.extend(decode_sub(u))
    all_links = list(dict.fromkeys(all_links))
    print(f"🚀 Проверка {len(all_links)} ссылок...")

    # Проверяем только первые 200 для теста скорости, если их слишком много
    test_links = all_links[:300] 
    
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as ex:
        results = list(ex.map(check_link, test_links))
    
    valid = [r for r in results if r]
    with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
        f.write("\n".join(valid))
    print(f"🏁 Сохранено рабочих: {len(valid)}")

if __name__ == "__main__":
    main()
