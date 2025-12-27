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
TIMEOUT = 15          # Увеличил таймаут
MAX_WORKERS = 2       # Минимум потоков, чтобы GitHub не блокировал порты

def setup_xray():
    if not os.path.exists("xray"):
        url = "https://github.com/XTLS/Xray-core/releases/latest/download/Xray-linux-64.zip"
        r = requests.get(url)
        with open("xray.zip", "wb") as f: f.write(r.content)
        with zipfile.ZipFile("xray.zip", 'r') as zip_ref: zip_ref.extractall(".")
        os.chmod("xray", 0o755)

def decode_sub(url):
    try:
        headers = {'User-Agent': 'v2rayNG/1.8.5'}
        resp = requests.get(url, headers=headers, timeout=10)
        content = resp.text
        if "vless://" not in content:
            try:
                content = base64.b64decode(content + "==").decode('utf-8', errors='ignore')
            except: pass
        return re.findall(r'vless://[^\s#|\n|"]+', content)
    except: return []

def check_link(link):
    # Ищем свободный порт
    with socket.socket() as s:
        s.bind(('', 0))
        port = s.getsockname()[1]
    
    try:
        parsed = urlparse(link.split('#')[0])
        p = {k: v[0] for k, v in parse_qs(parsed.query).items()}
        
        # Генерируем конфиг
        config = {
            "log": {"loglevel": "none"},
            "inbounds": [{"port": port, "protocol": "socks", "settings": {"udp": True}}],
            "outbounds": [{
                "protocol": "vless",
                "settings": {"vnext": [{"address": parsed.hostname, "port": int(parsed.port or 443), "users": [{"id": parsed.username, "encryption": p.get('encryption', 'none'), "flow": p.get('flow', '')}]}]},
                "streamSettings": {
                    "network": p.get('type', 'tcp'),
                    "security": p.get('security', 'none'),
                    "tlsSettings": {"serverName": p.get('sni', '')},
                    "realitySettings": {"serverName": p.get('sni', ''), "publicKey": p.get('pbk', ''), "shortId": p.get('sid', ''), "spiderX": p.get('spx', '')},
                    "wsSettings": {"path": p.get('path', '/')},
                    "grpcSettings": {"serviceName": p.get('serviceName', '')}
                }
            }]
        }
        
        conf_name = f"c_{port}.json"
        with open(conf_name, 'w') as f: json.dump(config, f)
        
        # Запуск с очисткой окружения
        proc = subprocess.Popen([XRAY_BIN, "run", "-c", conf_name], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        
        time.sleep(5) # Даем Xray время надежно подключиться
        
        is_ok = False
        try:
            # Используем curl, так как он в GitHub Actions работает стабильнее с прокси
            # -s (тихо), -o /dev/null (не выводить тело), -w %{http_code} (только код ответа)
            cmd = f"curl -s -o /dev/null -w '%{{http_code}}' --socks5h 127.0.0.1:{port} {CHECK_URL} --max-time {TIMEOUT}"
            result = subprocess.check_output(cmd, shell=True).decode().strip()
            
            if result in ["200", "204"]:
                print(f"✅ РАБОТАЕТ: {parsed.hostname}")
                is_ok = True
        except:
            pass
        
        proc.terminate()
        proc.wait()
        if os.path.exists(conf_name): os.remove(conf_name)
        return link if is_ok else None
    except:
        return None

def main():
    setup_xray()
    with open(INPUT_FILE, 'r') as f:
        urls = [l.strip() for l in f if l.strip()]
    
    all_links = []
    for u in urls: all_links.extend(decode_sub(u))
    all_links = list(dict.fromkeys(all_links))
    
    # Проверяем порцию серверов
    to_check = all_links[:100] # Начни с маленькой порции, чтобы убедиться, что метод curl работает
    print(f"Проверка {len(to_check)} серверов через curl + xray...")
    
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as ex:
        results = list(ex.map(check_link, to_check))
    
    valid = [r for r in results if r]
    with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
        f.write("\n".join(valid))
    print(f"Итог: рабочих {len(valid)}")

if __name__ == "__main__":
    main()
