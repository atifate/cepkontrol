"""Real Tk pairing lifecycle with synthetic video and recorded input."""
import base64
import io
import json
import os
from pathlib import Path
import queue
import sys
import tempfile
import threading
import time
import tkinter as tk
sys.path.insert(0,str(Path(__file__).resolve().parent.parent))
from PIL import Image
import app as app_module
from transport import Session

commands=queue.Queue()
for_stdin=threading.Thread(target=lambda:[commands.put(line.strip()) for line in sys.stdin],daemon=True)
for_stdin.start()
printing=threading.Lock()


def report(kind,value=None):
    with printing:
        print(json.dumps({'type':kind,'value':value}),flush=True)


image=io.BytesIO()
test_image = Image.effect_noise((1280,720),80).convert('RGB') if os.environ.get('MOBILE_NOISE') else Image.new('RGB',(1280,720),'#243750')
test_image.save(image,'JPEG',quality=65)
frame=base64.b64encode(image.getvalue()).decode()


def capture(self):
    while not self.closed.is_set():
        if self.approved.wait(.1):
            try:
                if self.frame_ack and not self.frame_received.wait(.1):
                    continue
                if self.frame_ack and 0 < self.frame_id <= 3:
                    report('video_ack')
                self.frame_id += 1
                self.pending_frame = self.frame_id
                self.frame_sent_at = time.monotonic()
                self.frame_received.clear()
                self.send({'type':'frame','session':self.session_id,'frame_id':self.frame_id,'jpeg':frame})
            except Exception:
                return
            self.closed.wait(.15)


Session.capture=capture
Session.apply_input=lambda self,event:report('input',event)
temporary=tempfile.TemporaryDirectory()
app_module.CONFIG=Path(temporary.name)/'settings.json'
restart=False
first=True
while True:
    root=tk.Tk()
    application=app_module.App(root)
    root.withdraw()
    application.server.set(os.environ.get('MOBILE_TEST_WS','ws://127.0.0.1:18766'))
    original_emit=application.emit
    def emit(session,kind,payload):
        original_emit(session,kind,payload)
        if kind in ('accepted','consent','ended','error'):
            report(kind, payload if kind=='error' else None)
    application.emit=emit
    if first:
        application.pair_phone()
    else:
        report('restarted')
    reported=False
    restart=False
    def tick():
        global reported,restart
        if application.consent:
            report('unexpected_consent')
        if application.phone_popup:
            application.phone_popup.withdraw()
        if not reported and application.code.get() and application.enrollment:
            report('ready',{'code':application.code.get(),**application.enrollment})
            reported=True
        try:
            command=commands.get_nowait()
        except queue.Empty:
            command=None
        if command=='restart':
            restart=True
            application.quit()
            return
        if command=='revoke':
            for phone in application.trust.phones():
                application.trust.remove(phone['id'])
            application.disconnect()
            report('revoked')
        if command=='pause':
            application.disconnect()
            report('paused')
        if command=='resume':
            application.trust.enable(True)
            application.resume_host()
            report('resumed')
        root.after(30,tick)
    root.after(30,tick)
    root.mainloop()
    if not restart:
        break
    first=False
temporary.cleanup()
