"""Measure relay stability with synthetic opaque traffic; no desktop or keys."""
import argparse
import json
import os
from pathlib import Path
import secrets
import sys
import threading
import time
import websocket

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from defaults import DEFAULT_SERVER

parser = argparse.ArgumentParser()
parser.add_argument('--url', default=DEFAULT_SERVER)
parser.add_argument('--seconds', type=float, default=40)
parser.add_argument('--size', type=int, default=250000)
parser.add_argument('--paced', action='store_true')
args = parser.parse_args()
room = str(secrets.randbelow(900000000) + 100000000)
host = websocket.create_connection(args.url+'/host/'+room, timeout=8, http_no_proxy=['*'])
assert 'ready' in host.recv()
viewer = websocket.create_connection(args.url+'/viewer/'+room, timeout=8, http_no_proxy=['*'])
assert 'ready' in viewer.recv()
host.settimeout(30 if args.paced else 2)
viewer.settimeout(2)
stop = threading.Event()
credit = threading.Event()
credit.set()
stats = {'sent':0, 'received':0, 'max_send_seconds':0, 'max_gap_seconds':0, 'errors':[]}
def read(ws, receiving):
    last = time.monotonic()
    while not stop.is_set():
        try:
            data = ws.recv()
            if stop.is_set(): return
            if not data:
                stats['errors'].append(('viewer' if receiving else 'host')+' closed')
                return
            if receiving:
                stats['received'] += 1
                now = time.monotonic()
                stats['max_gap_seconds'] = round(max(stats['max_gap_seconds'], now-last),3)
                last = now
                if args.paced: viewer.send_binary(b'ack')
            elif args.paced and data == b'ack':
                credit.set()
        except websocket.WebSocketTimeoutException:
            continue
        except Exception as exc:
            stats['errors'].append(('viewer' if receiving else 'host')+': '+type(exc).__name__)
            return
threads = [threading.Thread(target=read,args=(host,False)), threading.Thread(target=read,args=(viewer,True))]
for thread in threads: thread.start()
packet = os.urandom(args.size)
started = time.monotonic()
try:
    while time.monotonic()-started < args.seconds and not stats['errors']:
        if args.paced:
            if not credit.wait(35):
                stats['errors'].append('frame acknowledgement timeout')
                break
            credit.clear()
        before = time.monotonic()
        try:
            host.send_binary(packet)
            stats['sent'] += 1
            stats['max_send_seconds'] = round(max(stats['max_send_seconds'],time.monotonic()-before),3)
        except Exception as exc:
            stats['errors'].append('send: '+type(exc).__name__)
            break
        stop.wait(.12)
finally:
    time.sleep(1)
    stop.set()
    host.close(timeout=1)
    viewer.close(timeout=1)
    for thread in threads: thread.join(timeout=3)
stats['seconds'] = round(time.monotonic()-started,1)
stats['frame_bytes'] = args.size
stats['paced'] = args.paced
print(json.dumps(stats))
