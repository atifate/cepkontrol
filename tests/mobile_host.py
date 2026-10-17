"""Synthetic desktop fixture. Records commands instead of injecting OS input."""
import base64
import io
import json
import os
import sys
import threading
import time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from PIL import Image, ImageDraw
from transport import Session
from wire import make_code

code, data = make_code(os.environ.get('MOBILE_TEST_WS', 'ws://127.0.0.1:18766'))
output_lock = threading.Lock()


def report(kind, value=None):
    with output_lock:
        print(json.dumps({'type': kind, 'value': value}), flush=True)


def emit(kind, payload):
    if kind == 'ready':
        report('ready', code)
    elif kind == 'consent':
        report('consent')
        host.accept(True)
    elif kind == 'error':
        report('error', payload)


host = Session(data, 'host', emit)
host.apply_input = lambda event: report('input', event)


def capture():
    image = Image.new('RGB', (1280, 720), '#152238')
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle((80, 70, 1200, 650), radius=35, fill='#243750', outline='#46dfb2', width=5)
    draw.rectangle((120, 120, 550, 400), fill='#46dfb2')
    draw.text((130, 430), 'CepKontrol - synthetic desktop test', fill='white', font_size=32)
    stream = io.BytesIO()
    image.save(stream, 'JPEG')
    encoded = base64.b64encode(stream.getvalue()).decode()
    while not host.closed.is_set():
        if host.approved.wait(.1):
            try:
                host.send({'type': 'frame', 'session': host.session_id, 'jpeg': encoded})
            except Exception:
                return
            host.closed.wait(.15)


host.capture = capture
host.start()
try:
    while not host.closed.wait(.2):
        pass
finally:
    host.close()
