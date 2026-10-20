import base64
import io
import os
import queue
import subprocess
import sys
import time
import unittest
import socket
import tempfile
import secrets
from urllib.parse import urlsplit
from unittest.mock import patch
from unittest.mock import MagicMock

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from PIL import Image
from wire import Cipher, make_code, parse_code, validate_url
from transport import Session
from pairing import TrustedStore, phone_proof, session_key
from app import App


def wait_for(events, kind, timeout=10):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        try:
            k, value = events.get(timeout=.2)
            if k == 'error':
                raise AssertionError(value)
            if k == kind:
                return value
        except queue.Empty:
            pass
    raise AssertionError(f'Timed out waiting for {kind}')


class ProtocolTests(unittest.TestCase):
    def test_code_and_cipher(self):
        code, data = make_code('ws://127.0.0.1:8765')
        self.assertLess(len(code), 45)
        self.assertEqual(parse_code(code, data['url']), data)
        cipher = Cipher(data['key'])
        packet = cipher.pack({'type': 'input', 'seq': 1})
        self.assertEqual(cipher.unpack(packet)['seq'], 1)
        with self.assertRaises(Exception):
            cipher.unpack(packet[:-1] + bytes([packet[-1] ^ 1]))
        _, other = make_code(data['url'])
        with self.assertRaises(Exception):
            Cipher(other['key']).unpack(packet)

    def test_invalid_code_and_public_plaintext(self):
        for code in ('', 'AD2.123.a', 'AD1.e30', 'AD2.' + 'A' * 3000):
            with self.assertRaises(ValueError):
                parse_code(code)
        with self.assertRaises(ValueError):
            validate_url('ws://example.com')
        with self.assertRaises(ValueError):
            validate_url('wss://user:password@example.com')
        self.assertEqual(validate_url('ws://100.95.233.35:8765'), 'ws://100.95.233.35:8765')

    def test_viewer_replaces_idle_trusted_phone_listener(self):
        app = App.__new__(App)
        app.remote_code = MagicMock(get=lambda: 'AD2.123456789.' + 'A' * 26)
        app.server = MagicMock(get=lambda: 'wss://example.com')
        app.session = MagicMock(role='host', trusted_store=object())
        app.session.approved.is_set.return_value = False
        app.viewer_return_to_host = False
        app.disconnect = MagicMock()
        app.begin = MagicMock(return_value=True)
        with patch('app.parse_code', return_value={'url': 'wss://example.com', 'room': '123456789', 'key': '00' * 32}):
            app.connect()
        self.assertTrue(app.viewer_return_to_host)
        app.disconnect.assert_called_once_with(pause=False)
        app.begin.assert_called_once_with({'url': 'wss://example.com', 'room': '123456789', 'key': '00' * 32}, 'viewer')


class RelayTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.url = os.environ.get('RELAY_TEST_URL', 'ws://127.0.0.1:18765')
        cls.dns_patch = None
        if os.environ.get('RELAY_PUBLIC_IP'):
            # Preserve TLS hostname verification while forcing the public route,
            # rather than our machine's private Tailscale DNS route.
            original_lookup = socket.getaddrinfo
            hostname = urlsplit(cls.url).hostname
            def public_lookup(host, port, *args, **kwargs):
                if host == hostname:
                    host = os.environ['RELAY_PUBLIC_IP']
                return original_lookup(host, port, *args, **kwargs)
            cls.dns_patch = patch('socket.getaddrinfo', side_effect=public_lookup)
            cls.dns_patch.start()
        cls.process = None
        if 'RELAY_TEST_URL' not in os.environ:
            env = dict(os.environ, PORT='18765')
            cls.process = subprocess.Popen([sys.executable, 'relay.py'], env=env,
                                           stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            for _ in range(50):
                try:
                    with socket.create_connection(('127.0.0.1', 18765), timeout=.2):
                        break
                except OSError:
                    time.sleep(.1)

    @classmethod
    def tearDownClass(cls):
        if cls.process:
            cls.process.terminate()
            cls.process.communicate(timeout=5)
        if cls.dns_patch:
            cls.dns_patch.stop()

    def setUp(self):
        self.sessions = []

    def tearDown(self):
        for session in self.sessions:
            session.close()

    def new_session(self, data, role, trusted_store=None):
        events = queue.Queue()
        session = Session(data, role, lambda k, p: events.put((k, p)), trusted_store=trusted_store)
        # Synthetic frames make the test independent of the user's desktop.
        def capture():
            session.monitor = {'left': 0, 'top': 0, 'width': 640, 'height': 480}
            while not session.closed.is_set():
                if session.approved.wait(.1):
                    output = io.BytesIO()
                    Image.new('RGB', (320, 200), '#22aa77').save(output, 'JPEG')
                    try:
                        session.send({'type': 'frame', 'session': session.session_id,
                                      'jpeg': base64.b64encode(output.getvalue()).decode()})
                    except Exception:
                        return
                    session.closed.wait(.1)
        if role == 'host':
            session.capture = capture
        self.sessions.append(session)
        session.start()
        wait_for(events, 'ready')
        return session, events

    def test_consent_frames_input_replay_and_release(self):
        _, data = make_code(self.url)
        host, he = self.new_session(data, 'host')
        viewer, ve = self.new_session(data, 'viewer')
        wait_for(he, 'consent')
        with patch('transport.mouse.keyDown') as down, patch('transport.mouse.platformModule._keyUp') as up:
            # A viewer cannot inject input before the user accepts.
            viewer.send({'type': 'input', 'session': None, 'seq': 1,
                         'event': {'kind': 'keydown', 'key': 'a'}})
            time.sleep(.15)
            down.assert_not_called()
            host.accept(True)
            wait_for(ve, 'accepted')
            image = wait_for(ve, 'frame')
            self.assertEqual(image.size, (320, 200))
            event = {'kind': 'keydown', 'key': 'a'}
            viewer.input(event)
            for _ in range(50):
                if down.called:
                    break
                time.sleep(.02)
            down.assert_called_once_with('a')
            # Replaying the same authenticated command must not inject it twice.
            viewer.send({'type': 'input', 'session': viewer.session_id,
                         'seq': viewer.seq, 'event': event})
            time.sleep(.15)
            down.assert_called_once()
            host.control = False
            host.release_inputs()
            up.assert_called_once_with('a')
            viewer.input({'kind': 'keydown', 'key': 'b'})
            time.sleep(.15)
            down.assert_called_once()
        viewer.close()
        wait_for(he, 'ended')
        self.assertFalse(host.held_keys)

    def test_reject(self):
        _, data = make_code(self.url)
        host, he = self.new_session(data, 'host')
        viewer, ve = self.new_session(data, 'viewer')
        wait_for(he, 'consent')
        host.accept(False)
        end = time.monotonic() + 5
        while not viewer.closed.is_set() and time.monotonic() < end:
            time.sleep(.05)
        self.assertTrue(viewer.closed.is_set())
        self.assertFalse(viewer.approved.is_set())

    def test_empty_browser_close_is_not_a_network_failure(self):
        import websocket
        _, data = make_code(self.url)
        host = websocket.create_connection(self.url+'/host/'+data['room'], timeout=5)
        viewer = None
        try:
            host.recv()
            viewer = websocket.create_connection(self.url+'/viewer/'+data['room'], timeout=5)
            viewer.recv()
            viewer.send_frame(websocket.ABNF.create_frame(b'',websocket.ABNF.OPCODE_CLOSE))
            viewer.recv_data(control_frame=True)
            viewer.shutdown()
            opcode, payload = host.recv_data(control_frame=True)
            self.assertEqual(opcode,websocket.ABNF.OPCODE_CLOSE)
            self.assertEqual(int.from_bytes(payload[:2],'big'),1000)
        finally:
            host.close(timeout=1)
            host.shutdown()
            if viewer:
                viewer.close(timeout=1)
                viewer.shutdown()

    def test_trusted_phone_bootstrap_rotation_replay_and_revocation(self):
        import websocket
        from pathlib import Path
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'phones.dat'
            store = TrustedStore(path)
            saved = store.configure(self.url)
            enrollment = store.enrollment()
            host, events = self.new_session(saved['data'], 'host', store)
            viewer = websocket.create_connection(self.url+'/viewer/'+saved['data']['room'], timeout=5)
            self.assertIn('ready', viewer.recv())
            base = Cipher(saved['data']['key'])
            viewer.send_binary(base.pack({'type':'hello','name':'Test phone','phone_id':enrollment['id']}))
            challenge = base.unpack(viewer.recv())['challenge']
            self.assertFalse(host.approved.is_set())
            proof = phone_proof(enrollment['token'],challenge,saved['data']['room'],enrollment['id'])
            viewer.send_binary(base.pack({'type':'phone_proof','proof':proof}))
            private = Cipher(session_key(enrollment['token'],challenge,saved['data']['room'],enrollment['id']))
            accepted_packet = viewer.recv()
            accepted = private.unpack(accepted_packet)
            self.assertEqual(accepted['type'],'accepted')
            token = accepted['pairing']['token']
            self.assertNotEqual(token,enrollment['token'])
            with self.assertRaises(Exception):
                base.unpack(accepted_packet)
            self.assertEqual(private.unpack(viewer.recv())['type'],'frame')
            self.assertNotIn(enrollment['token'].encode(),path.read_bytes())
            self.assertNotIn(token.encode(),path.read_bytes())
            viewer.close()
            wait_for(events,'ended')
            # Server removes the old room after its WebSocket close handshake.
            time.sleep(.2)
            reloaded = TrustedStore(path)
            self.assertEqual(reloaded.phones()[0]['id'],enrollment['id'])
            host, events = self.new_session(saved['data'],'host',reloaded)
            viewer = websocket.create_connection(self.url+'/viewer/'+saved['data']['room'],timeout=5)
            viewer.recv()
            viewer.send_binary(base.pack({'type':'hello','name':'Test phone','phone_id':enrollment['id']}))
            new_challenge = base.unpack(viewer.recv())['challenge']
            self.assertNotEqual(new_challenge,challenge)
            # Captured proof from a previous session must never log in again.
            viewer.send_binary(base.pack({'type':'phone_proof','proof':proof}))
            self.assertEqual(base.unpack(viewer.recv())['type'],'rejected')
            self.assertFalse(host.approved.is_set())
            viewer.close()
            wait_for(events,'ended')
            reloaded.remove(enrollment['id'])
            self.assertFalse(reloaded.valid(enrollment['id']))
            self.assertFalse(reloaded.enabled)
            self.assertIsNone(reloaded.authenticate(enrollment['id'],secrets.token_hex(32),saved['data']['room'],proof,'Revoked phone'))


if __name__ == '__main__':
    unittest.main(verbosity=2)
