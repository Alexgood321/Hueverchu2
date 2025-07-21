import os
import socket
import time
import yaml
import requests
import base64
import json
from urllib.parse import urlparse, parse_qs
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime

MAX_PROXY_COUNT = 10
TIMEOUT = 5
PROXY_SOURCE = "https://raw.githubusercontent.com/MatinGhanbari/v2ray-configs/main/subscriptions/v2ray/super-sub.txt"

output_dir = "output"
log_dir = "logs"
os.makedirs(output_dir, exist_ok=True)
os.makedirs(log_dir, exist_ok=True)

def get_timestamp():
    return datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC")

def timestamp_file():
    return datetime.utcnow().strftime("%Y-%m-%d_%H")

def decode_sub(content):
    try:
        if content.startswith("sub://"):
            content = content[6:]
        decoded = base64.b64decode(content + "==").decode()
        return decoded.splitlines()
    except Exception as e:
        return []

def extract_host_port(line):
    try:
        parsed = urlparse(line)
        return parsed.hostname, parsed.port
    except:
        return None, None

def check_latency(host, port):
    try:
        start = time.time()
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(TIMEOUT)
        sock.connect((host, port))
        sock.send(b"HEAD / HTTP/1.1\r\nHost: example.com\r\n\r\n")
        sock.recv(1024)
        latency = (time.time() - start) * 1000
        sock.close()
        return True, latency
    except:
        return False, None

def convert_to_clash(line):
    if line.startswith("vmess://"):
        try:
            raw = base64.b64decode(line[8:] + "==").decode("utf-8")
            j = json.loads(raw)
            return {
                "name": f"vmess-{j['add']}-{j['port']}",
                "type": "vmess",
                "server": j["add"],
                "port": int(j["port"]),
                "uuid": j["id"],
                "network": j.get("net", "tcp"),
                "tls": j.get("tls", "false") == "true"
            }
        except:
            return None
    return None

def main():
    log = [f"[{get_timestamp()}] Start"]
    try:
        r = requests.get(PROXY_SOURCE, timeout=10)
        r.raise_for_status()
        proxy_lines = decode_sub(r.text.strip())
        log.append(f"[{get_timestamp()}] Loaded {len(proxy_lines)} proxies")
    except Exception as e:
        log.append(f"Failed to fetch proxy list: {str(e)}")
        return

    valid = []
    skipped = []

    with ThreadPoolExecutor(max_workers=30) as ex:
        futures = {}
        for line in proxy_lines:
            host, port = extract_host_port(line)
            if host and port:
                futures[ex.submit(check_latency, host, port)] = line
            else:
                skipped.append(line)

        for future in futures:
            line = futures[future]
            try:
                alive, latency = future.result()
                if alive and latency < 5000:
                    valid.append((line, latency))
                    log.append(f"[{get_timestamp()}] ✅ {line[:50]}... - {latency:.1f}ms")
                else:
                    skipped.append(line)
                    log.append(f"[{get_timestamp()}] ❌ {line[:50]}...")
            except:
                skipped.append(line)

    valid.sort(key=lambda x: x[1])
    best = [line for line, _ in valid[:MAX_PROXY_COUNT]]
    clash_configs = [convert_to_clash(line) for line in best if convert_to_clash(line)]

    # Write outputs
    with open(os.path.join(output_dir, "Server.txt"), "w") as f:
        f.write("\n".join(best))
    with open(os.path.join(output_dir, "skipped.txt"), "w") as f:
        f.write("\n".join(skipped))
    with open(os.path.join(output_dir, "clash.yaml"), "w") as f:
        yaml.dump({"proxies": clash_configs}, f, sort_keys=False)
    with open(os.path.join(log_dir, f"ping_debug_{timestamp_file()}.txt"), "w") as f:
        f.write("\n".join(log))

    print(f"✅ Saved {len(best)} proxies. Skipped: {len(skipped)}")

if __name__ == "__main__":
    main()
