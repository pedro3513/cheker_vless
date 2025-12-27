import requests
import base64
import re
import os
import socket
from urllib.parse import urlparse
from concurrent.futures import ThreadPoolExecutor

# --- НАСТРОЙКИ ---
INPUT_FILE = "input.txt"
OUTPUT_FILE = "output.txt"
TIMEOUT = 3          # Секунды на проверку одного сервера
MAX_WORKERS = 50     # Много потоков для быстрой проверки

def decode_sub(url):
    headers = {'User-Agent': 'v2rayNG/1.8.5'}
    try:
        resp = requests.get(url, headers=headers, timeout=10)
        content = resp.text.strip().replace(' ', '')
        if "vless://" not in content:
            try:
                padded = content + "=" * (4 - len(content) % 4) if len(content) % 4 else content
                decoded = base64.b64decode(padded).decode('utf-8', errors='ignore')
            except: decoded = content
        else: decoded = content
        return re.findall(r'vless://[^\s#|\n|"]+', decoded)
    except: return []

def is_alive(link):
    """Проверяет, отвечает ли сервер по TCP на указанном порту"""
    try:
        parsed = urlparse(link.split('#')[0])
        host = parsed.hostname
        port = parsed.port or 443
        
        # Попытка установить TCP соединение
        with socket.create_connection((host, port), timeout=TIMEOUT):
            return True
    except:
        return False

def check_link(link):
    if is_alive(link):
        # Если сервер жив, возвращаем его с флагом страны (по IP)
        return link
    return None

def main():
    if not os.path.exists(INPUT_FILE): return
    with open(INPUT_FILE, 'r') as f:
        urls = [l.strip() for l in f if l.strip()]
    
    print("📥 Собираю ссылки...")
    all_links = []
    for u in urls:
        all_links.extend(decode_sub(u))
    
    all_links = list(dict.fromkeys(all_links))
    total = len(all_links)
    print(f"🚀 Найдено {total}. Начинаю фильтрацию живых серверов...")

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as ex:
        results = list(ex.map(check_link, all_links))
    
    valid = [r for r in results if r]
    
    # Сохраняем результат
    with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
        f.write("\n".join(valid))
    
    print(f"🏁 Из {total} серверов живыми оказались: {len(valid)}")

if __name__ == "__main__":
    main()
