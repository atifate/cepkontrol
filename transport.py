import base64
import io
import logging
import secrets
import socket
import threading
import time

import mss
import pyautogui as mouse
import websocket
from PIL import Image
from wire import Cipher
from wininput import type_unicode
from defaults import DEFAULT_SERVER, PRIVATE_RELAY

mouse.PAUSE = 0
log = logging.getLogger('acikdestek.transport')


class Session:
    """One consent-bound session. All UI notifications go through emit()."""
    def __init__(self, data, role, emit, trusted_store=None):
        self.data, self.role, self.emit = data, role, emit
        self.cipher = Cipher(data['key'])
        self.ws = None
        self.closed = threading.Event()
        self.approved = threading.Event()
        self.session_id = None
        self.seq = 0
        self.last_seq = -1
        self.held_keys = set()
        self.held_buttons = set()
        self.input_lock = threading.RLock()
        self.send_lock = threading.Lock()
        self.control = True
        self.pending = False
        self.last_input = time.monotonic()
        self.trusted_store = trusted_store
        self.phone_id = None
        self.challenge = None
        self.challenge_until = 0
        self.frame_ack = False
        self.frame_received = threading.Event()
        self.frame_received.set()
        self.frame_id = 0
        self.pending_frame = None
        self.frame_sent_at = 0
        self.frame_latency = .3
        self.send_latency = 0
        self.started_at = time.monotonic()
        self.frames_sent = 0

    def start(self):
        threading.Thread(target=self.run, daemon=True).start()

    def send(self, packet):
        if self.closed.is_set() or not self.ws:
            return
        with self.send_lock:
            started = time.monotonic()
            self.ws.send_binary(self.cipher.pack(packet))
            if packet.get('type') == 'frame':
                self.send_latency = time.monotonic() - started
                self.frames_sent += 1

    def run(self):
        try:
            routes = [('public', self.data['url'])]
            if self.data['url'] == DEFAULT_SERVER:
                routes.insert(0, ('private', PRIVATE_RELAY))
            for route, url in routes:
                candidate = None
                try:
                    candidate = websocket.create_connection(
                        f"{url}/{self.role}/{self.data['room']}",
                        timeout=3 if route=='private' else 8,
                        enable_multithread=True, http_no_proxy=['*'])
                    ready = candidate.recv()
                    if not isinstance(ready, str) or 'ready' not in ready:
                        raise RuntimeError('Sunucu bağlantıyı kabul etmedi.')
                    self.ws = candidate
                    break
                except Exception:
                    if candidate:
                        try:
                            candidate.close(timeout=1)
                        finally:
                            candidate.shutdown()
                    if route == routes[-1][0]:
                        raise
                    log.info('route_fallback role=%s from=%s', self.role, route)
            # This timeout also governs writes. A 2-second socket timeout used
            # to abort large video frames on a slow link, ending the session.
            self.ws.settimeout(30)
            if self.closed.is_set():
                return
            self.emit('ready', None)
            log.info('connected role=%s route=%s', self.role, route)
            if self.role == 'viewer':
                self.send({'type': 'hello', 'name': socket.gethostname()[:64], 'frame_ack': True})
            else:
                threading.Thread(target=self.capture, daemon=True).start()
            deadline = time.monotonic() + (300 if self.role == 'host' else 60)
            last_packet = time.monotonic()
            while not self.closed.is_set():
                if self.challenge and time.monotonic() > self.challenge_until:
                    self.accept(False)
                    break
                if not self.approved.is_set() and not self.trusted_store and time.monotonic() > deadline:
                    raise TimeoutError('Bağlantı/onay süresi doldu. Yeni kod oluşturun.')
                try:
                    opcode, packet = self.ws.recv_data(control_frame=True)
                    last_packet = time.monotonic()
                    if opcode == websocket.ABNF.OPCODE_CLOSE:
                        code = int.from_bytes(packet[:2], 'big') if len(packet) >= 2 else 1005
                        log.info('peer_closed role=%s code=%s', self.role, code)
                        break
                    if opcode in (websocket.ABNF.OPCODE_PING, websocket.ABNF.OPCODE_PONG):
                        continue
                except websocket.WebSocketTimeoutException:
                    if time.monotonic()-last_packet > 75:
                        raise TimeoutError('Sunucudan yanıt alınamıyor.')
                    continue
                if not packet:
                    break
                try:
                    message = self.cipher.unpack(packet)
                except Exception:
                    continue
                self.receive(message)
        except Exception as exc:
            if not self.closed.is_set():
                log.info('connection_error role=%s exception=%s', self.role, type(exc).__name__)
                message = str(exc) if str(exc).startswith('Bağlantı/onay süresi') else 'Bağlantı kurulamadı veya kesildi. Sunucu adresini ve ağ bağlantısını kontrol edin.'
                self.emit('error', message)
        finally:
            log.info('session_ended role=%s seconds=%.1f frames=%s', self.role, time.monotonic()-self.started_at, self.frames_sent)
            self.close()
            self.emit('ended', None)

    def receive(self, msg):
        kind = msg.get('type')
        if self.role == 'host':
            if kind == 'hello' and not self.pending and not self.approved.is_set():
                self.pending = True
                self.phone_name = str(msg.get('name', 'Telefon'))[:64]
                self.frame_ack = msg.get('frame_ack') is True
                identity = msg.get('phone_id')
                if identity and self.trusted_store:
                    if not isinstance(identity, str) or not self.trusted_store.valid(identity):
                        self.accept(False)
                        return
                    self.phone_id = identity
                    self.challenge = secrets.token_hex(32)
                    self.challenge_until = time.monotonic() + 30
                    self.send({'type': 'phone_challenge', 'challenge': self.challenge})
                else:
                    self.emit('consent', self.phone_name)
            elif kind == 'phone_proof' and self.challenge and not self.approved.is_set():
                credential = None
                if time.monotonic() < self.challenge_until:
                    credential = self.trusted_store.authenticate(self.phone_id, self.challenge, self.data['room'], msg.get('proof'), self.phone_name)
                self.challenge = None
                if credential:
                    self.cipher = Cipher(credential['session_key'])
                    self.accept(True, self.control, credential)
                    self.emit('paired', self.phone_name)
                else:
                    self.accept(False)
            elif kind == 'frame_ack' and self.approved.is_set() and msg.get('session') == self.session_id:
                if type(msg.get('frame_id')) is int and msg['frame_id'] == self.pending_frame:
                    self.frame_latency = .7*self.frame_latency + .3*(time.monotonic()-self.frame_sent_at)
                    self.pending_frame = None
                    self.frame_received.set()
            elif kind == 'input' and self.approved.is_set() and msg.get('session') == self.session_id:
                seq = msg.get('seq')
                if type(seq) is int and seq > self.last_seq:
                    self.last_seq = seq
                    self.last_input = time.monotonic()
                    event = msg.get('event', {})
                    if event.get('kind') == 'heartbeat':
                        self.send({'type':'heartbeat', 'session':self.session_id})
                    else:
                        self.apply_input(event)
        elif kind == 'accepted' and not self.approved.is_set():
            self.session_id = msg['session']
            self.approved.set()
            self.emit('accepted', None)
        elif kind == 'rejected':
            self.emit('error', 'Karşı taraf bağlantıyı reddetti.')
            self.close()
        elif kind == 'frame' and self.approved.is_set() and msg.get('session') == self.session_id:
            raw = base64.b64decode(msg['jpeg'], validate=True)
            if len(raw) < 3 * 1024 * 1024:
                image = Image.open(io.BytesIO(raw))
                if image.width <= 1920 and image.height <= 1920:
                    image.load()
                    self.emit('frame', image)
                    if type(msg.get('frame_id')) is int:
                        self.send({'type':'frame_ack', 'session':self.session_id, 'frame_id':msg['frame_id']})

    def accept(self, allowed, control=True, credential=None):
        if self.closed.is_set():
            return
        self.control = control
        if not allowed:
            self.send({'type': 'rejected'})
            self.close()
            return
        self.session_id = secrets.token_hex(16)
        message = {'type': 'accepted', 'session': self.session_id}
        if credential:
            message['pairing'] = {'id': credential['id'], 'token': credential['token'], 'name': socket.gethostname()[:64]}
        self.send(message)
        self.approved.set()
        log.info('approved role=%s frame_ack=%s', self.role, self.frame_ack)
        self.emit('accepted', None)

    def capture(self):
        try:
            with mss.mss() as screen:
                monitor = screen.monitors[1]
                self.monitor = monitor
                while not self.closed.is_set():
                    if not self.approved.wait(0.2):
                        continue
                    # Release held inputs if the viewer stops sending heartbeats.
                    if time.monotonic() - self.last_input > 4:
                        self.release_inputs()
                    if self.frame_ack and not self.frame_received.wait(.2):
                        if time.monotonic()-self.frame_sent_at > 40:
                            raise TimeoutError('Telefon görüntüyü doğrulamadı.')
                        continue
                    if self.closed.is_set():
                        break
                    shot = screen.grab(monitor)
                    image = Image.frombytes('RGB', shot.size, shot.rgb)
                    latency = self.frame_latency if self.frame_ack else self.send_latency
                    size, quality = ((1024,640),45) if latency > 1 else ((1280,800),55)
                    image.thumbnail(size)
                    output = io.BytesIO()
                    image.save(output, 'JPEG', quality=quality)
                    self.frame_id += 1
                    self.pending_frame = self.frame_id
                    self.frame_sent_at = time.monotonic()
                    self.frame_received.clear()
                    self.send({'type': 'frame', 'session': self.session_id,
                               'frame_id': self.frame_id, 'jpeg': base64.b64encode(output.getvalue()).decode()})
                    # Older phone clients do not acknowledge frames. Keep them
                    # compatible while lowering bitrate and responding to
                    # socket backpressure instead of building an endless queue.
                    self.closed.wait(.16 if self.frame_ack else max(.35, min(2, self.send_latency*1.5)))
        except Exception as exc:
            if not self.closed.is_set():
                log.info('capture_error exception=%s', type(exc).__name__)
                self.emit('error', f'Ekran paylaşımı durdu: {exc}')
                self.close()

    def input(self, event):
        if self.approved.is_set():
            with self.send_lock:
                self.seq += 1
                packet = {'type': 'input', 'session': self.session_id, 'seq': self.seq, 'event': event}
                if not self.closed.is_set():
                    self.ws.send_binary(self.cipher.pack(packet))

    def apply_input(self, event):
        with self.input_lock:
            if not self.control or self.closed.is_set():
                return
            kind = event.get('kind')
            try:
                if kind == 'release':
                    self.release_inputs()
                elif kind in ('move', 'down', 'up'):
                    x, y = float(event['x']), float(event['y'])
                    if not (0 <= x <= 1 and 0 <= y <= 1):
                        return
                    m = self.monitor
                    mouse.moveTo(m['left'] + round(x * (m['width'] - 1)),
                                 m['top'] + round(y * (m['height'] - 1)))
                    button = event.get('button', 'left')
                    if button not in ('left', 'middle', 'right'):
                        return
                    if kind == 'down':
                        mouse.mouseDown(button=button)
                        self.held_buttons.add(button)
                    elif kind == 'up':
                        mouse.mouseUp(button=button)
                        self.held_buttons.discard(button)
                elif kind == 'scroll':
                    mouse.scroll(max(-5, min(5, int(event['steps']))))
                elif kind == 'text':
                    text = event.get('text', '')
                    if isinstance(text, str) and len(text) <= 8 and text.isprintable():
                        type_unicode(text)
                elif kind in ('keydown', 'keyup'):
                    key = event.get('key')
                    if key in mouse.KEYBOARD_KEYS:
                        if kind == 'keydown':
                            mouse.keyDown(key)
                            self.held_keys.add(key)
                        else:
                            mouse.keyUp(key)
                            self.held_keys.discard(key)
            except mouse.FailSafeException:
                self.emit('error', 'Yerel fare ekran köşesine taşındı; güvenli durdurma etkinleşti.')
                self.close()
            except (KeyError, ValueError, TypeError):
                return

    def release_inputs(self):
        with self.input_lock:
            # Key release must work even when the local failsafe was triggered.
            for key in list(self.held_keys):
                mouse.platformModule._keyUp(key)
            for button in list(self.held_buttons):
                x, y = mouse.position()
                mouse.platformModule._mouseUp(x, y, button)
            self.held_keys.clear()
            self.held_buttons.clear()

    def close(self):
        self.closed.set()
        self.frame_received.set()
        self.release_inputs()
        if self.ws:
            try:
                self.ws.close(timeout=1)
            except Exception:
                pass
            finally:
                # recv_data() replies to a peer CLOSE and marks the client
                # disconnected. websocket-client.close() then returns early,
                # so explicitly release the underlying socket in that case.
                self.ws.shutdown()
