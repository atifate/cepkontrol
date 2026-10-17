"""A slow phone must not accumulate unbounded screenshots in the socket."""
import sys
from pathlib import Path
import threading
import time
import unittest
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from transport import Session
from wire import make_code

class Screen:
    monitors = [None, {'left':0,'top':0,'width':1280,'height':720}]
    def __enter__(self): return self
    def __exit__(self,*args): pass
    def grab(self,monitor): return SimpleNamespace(size=(1280,720),rgb=b'\x42\x58\x72'*(1280*720))

class VideoFlowTests(unittest.TestCase):
    def test_slow_phone_allows_only_one_unacknowledged_frame(self):
        _,data=make_code('ws://127.0.0.1:8765')
        session=Session(data,'host',lambda *args:None)
        session.frame_ack=True
        session.session_id='test-session'
        session.approved.set()
        frames=[]
        session.send=lambda packet:frames.append(packet)
        with patch('transport.mss.mss',return_value=Screen()):
            worker=threading.Thread(target=session.capture)
            worker.start()
            try:
                end=time.monotonic()+3
                while not frames and time.monotonic()<end:time.sleep(.01)
                self.assertEqual(len(frames),1)
                # Even a phone taking a second to display a frame must not
                # cause more frames to queue or an unauthenticated ACK to work.
                time.sleep(1)
                self.assertEqual(len(frames),1)
                session.receive({'type':'frame_ack','session':'wrong','frame_id':frames[0]['frame_id']})
                session.receive({'type':'frame_ack','session':session.session_id,'frame_id':999})
                time.sleep(.25)
                self.assertEqual(len(frames),1)
                session.receive({'type':'frame_ack','session':session.session_id,'frame_id':frames[0]['frame_id']})
                end=time.monotonic()+2
                while len(frames)<2 and time.monotonic()<end:time.sleep(.01)
                self.assertEqual(len(frames),2)
                # A replay of the first frame ACK cannot unblock the next one.
                session.receive({'type':'frame_ack','session':session.session_id,'frame_id':frames[0]['frame_id']})
                time.sleep(.25)
                self.assertEqual(len(frames),2)
            finally:
                session.close()
                worker.join(timeout=2)
            self.assertFalse(worker.is_alive())

if __name__=='__main__':unittest.main()
