import subprocess
import json
import time
import requests
import os
import socket
import base64
import re
import zipfile
from urllib.parse import urlparse, parse_qs
from concurrent.futures import ThreadPoolExecutor

# --- НАСТРОЙКИ ---
XRAY_BIN = "./xray"
INPUT_FILE = "input.txt"
OUTPUT_FILE = "output.txt"
CHECK_URL = "http://www.google.com/generate_204"
TIMEOUT = 10         
MAX_WORKERS = 4      # GitHub не даст проверять 50 серверов одновременно

def setup_xray():
    if not os.path.exists("xray"):
        url = "https://github.com/XTLS/Xray-core/releases/latest/download/Xray-linux-64.zip"
        r = requests.get(url)
        with open("xray.zip", "wb") as f: f.write(r.content)
        with zipfile.ZipFile("xray.zip", 'r') as zip_ref: zip_ref.extractall(".")
        os.chmod("xray", 0o755)

def decode_sub(url):
    try:
        resp = requests.get(url, timeout=10)
        content = resp.text
        if "vless://" not in content:
            content = base64.b64decode(content + "==").decode('utf-8', errors='ignore')
        return re.findall(r'vless://[^\s#|\n|"]+', content)
    except: return []

def check_link(link):
    # Берем случайный порт для теста
    with socket.socket() as s:
        s.bind(('', 0))
        port = s.getsockname()[1]
    
    try:
        parsed = urlparse(link.split('#')[0])
        params = {k: v[0] for k, v in parse_qs(parsed.query).items()}
        
        config = {
            "log": {"loglevel": "none"},
            "inbounds": [{"port": port, "protocol": "socks", "settings": {"udp": True}}],
            "outbounds": [{
                "protocol": "vless",
                "settings": {"vnext": [{"address": parsed.hostname, "port": int(parsed.port or 443), "users": [{"id": parsed.username, "encryption": params.get('encryption', 'none'), "flow": params.get('flow', '')}]}]},
                "streamSettings": {
                    "network": params.get('type', 'tcp'),
                    "security": params.get('security', 'none'),
                    "tlsSettings": {"serverName": params.get('sni', '')},
                    "realitySettings": {"serverName": params.get('sni', ''), "publicKey": params.get('pbk', ''), "shortId": params.get('sid', ''), "spiderX": params.get('spx', '')},
                    "wsSettings": {"path": params.get('path', '/')},
                    "grpcSettings": {"serviceName": params.get('serviceName', '')}
                }
            }]
        }
        
        c_file = f"c_{port}.json"
        with open(c_file, 'w') as f: json.dump(config, f)
        
        # Запускаем Xray
        proc = subprocess.Popen([XRAY_BIN, "run", "-c", c_file], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        
        res = None
        # Ждем запуска и пробуем скачать
        time.sleep(2)
        try:
            # Пытаемся сделать реальный запрос через этот прокси
            r = requests.get(CHECK_URL, proxies={'http': f'socks5h://127.0.0.1:{port}', 'https': f'socks5h://127.0.0.1:{port}'}, timeout=TIMEOUT)
            if r.status_code == 204 or r.status_code == 200:
                print(f"✅ РАБОТАЕТ: {parsed.hostname}")
                res = link
        except:
            pass
        
        proc.terminate()
        proc.wait()
        os.remove(c_file)
        return res
    except:
        return None

def main():
    setup_xray()
    with open(INPUT_FILE, 'r') as f:
        urls = [l.strip() for l in f if l.strip()]
    
    all_links = []
    for u in urls: all_links.extend(decode_sub(u))
    all_links = list(dict.fromkeys(all_links))
    
    print(f"Начинаю жесткую проверку {len(all_links)} серверов...")
    
    # Проверяем не все сразу (чтобы GitHub не забанил), а первые 150 самых свежих
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as ex:
        results = list(ex.map(check_link, all_links[:150]))
    
    valid = [r for r in results if r]
    with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
        f.write("\n".join(valid))
    print(f"Итог: из 150 проверенных реально работают {len(valid)}")

if __name__ == "__main__":
    main()
