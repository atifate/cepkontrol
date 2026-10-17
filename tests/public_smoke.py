"""Wait for public Funnel DNS, then test via a public ingress IP with valid TLS."""
import ipaddress
import json
import os
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from defaults import DEFAULT_SERVER

hostname = DEFAULT_SERVER.removeprefix('wss://')
started = time.monotonic()
while time.monotonic() - started < 600:
    url = f'https://cloudflare-dns.com/dns-query?name={hostname}&type=A'
    request = urllib.request.Request(url, headers={'accept': 'application/dns-json'})
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            data = json.load(response)
        addresses = [a['data'] for a in data.get('Answer', []) if a['type'] == 1]
        addresses = [ip for ip in addresses if ipaddress.ip_address(ip).is_global]
        if addresses:
            print('Public DNS ready:', addresses, flush=True)
            env = dict(os.environ, RELAY_TEST_URL=DEFAULT_SERVER, RELAY_PUBLIC_IP=addresses[0])
            result = subprocess.run([sys.executable, '-m', 'unittest', 'discover', '-s', 'tests', '-v'], env=env)
            sys.exit(result.returncode)
        print(f'Public DNS pending ({int(time.monotonic() - started)}s)', flush=True)
    except Exception as exc:
        print('DNS lookup waiting:', type(exc).__name__, flush=True)
    time.sleep(20)
raise SystemExit('Public DNS is still pending; public access has not been verified.')
