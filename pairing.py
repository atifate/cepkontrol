"""Revocable phone credentials, encrypted with Windows CurrentUser DPAPI."""
import ctypes
from ctypes import wintypes
import hashlib
import hmac
import json
import os
from pathlib import Path
import secrets
import threading
import time
from wire import make_code


class BLOB(ctypes.Structure):
    _fields_ = [('size', wintypes.DWORD), ('data', ctypes.POINTER(ctypes.c_ubyte))]


def protect(data, decrypt=False):
    buffer = ctypes.create_string_buffer(data)
    source = BLOB(len(data), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_ubyte)))
    result = BLOB()
    function = ctypes.windll.crypt32.CryptUnprotectData if decrypt else ctypes.windll.crypt32.CryptProtectData
    if not function(ctypes.byref(source), None, None, None, None, 1, ctypes.byref(result)):
        raise ctypes.WinError()
    try:
        return ctypes.string_at(result.data, result.size)
    finally:
        ctypes.windll.kernel32.LocalFree(ctypes.cast(result.data, ctypes.c_void_p))


def phone_proof(token, challenge, room, phone_id):
    message = f'AcikDestek/pair/v1\0{challenge}\0{room}\0{phone_id}'.encode()
    return hmac.new(bytes.fromhex(token), message, hashlib.sha256).hexdigest()


def session_key(token, challenge, room, phone_id):
    message = f'AcikDestek/session/v1\0{challenge}\0{room}\0{phone_id}'.encode()
    return hmac.new(bytes.fromhex(token), message, hashlib.sha256).hexdigest()


class TrustedStore:
    def __init__(self, path):
        self.path = Path(path)
        self.lock = threading.RLock()
        self.state = {'enabled': False, 'host': None, 'phones': {}}
        if self.path.exists():
            # Do not replace unreadable credentials with a fresh permissive state.
            self.state = json.loads(protect(self.path.read_bytes(), decrypt=True))
            if not isinstance(self.state.get('phones'), dict):
                raise ValueError('Telefon kaydı okunamadı.')

    @property
    def enabled(self):
        with self.lock:
            return bool(self.state['enabled'] and self.state['host'])

    def save(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix('.tmp')
        temporary.write_bytes(protect(json.dumps(self.state).encode()))
        os.replace(temporary, self.path)

    def host(self):
        with self.lock:
            return json.loads(json.dumps(self.state['host']))

    def configure(self, url):
        with self.lock:
            if not self.state['host'] or self.state['host']['data']['url'] != url:
                code, data = make_code(url)
                self.state = {'enabled': True, 'host': {'code': code, 'data': data}, 'phones': {}, 'control': self.control}
            self.state['enabled'] = True
            self.save()
            return self.host()

    def enable(self, enabled):
        with self.lock:
            self.state['enabled'] = bool(enabled)
            self.save()

    @property
    def control(self):
        with self.lock:
            return bool(self.state.get('control', True))

    def set_control(self, value):
        with self.lock:
            self.state['control'] = bool(value)
            self.save()

    def enrollment(self):
        with self.lock:
            now = time.time()
            self.state['phones'] = {i: p for i, p in self.state['phones'].items()
                                     if p['state'] == 'paired' or now-p['created'] < 600}
            for identity, phone in self.state['phones'].items():
                if phone['state'] == 'pending':
                    return {'id': identity, 'token': phone['token']}
            if len(self.state['phones']) >= 5:
                raise ValueError('En fazla 5 telefon kaydedilebilir. Ayarlar’dan eski bir telefonu kaldırın.')
            identity, token = secrets.token_hex(16), secrets.token_hex(32)
            self.state['phones'][identity] = {'token': token, 'created': now, 'state': 'pending', 'name': 'Yeni telefon'}
            self.save()
            return {'id': identity, 'token': token}

    def valid(self, identity):
        with self.lock:
            phone = self.state['phones'].get(identity)
            return bool(self.enabled and phone and (phone['state'] == 'paired' or time.time()-phone['created'] < 600))

    def authenticate(self, identity, challenge, room, proof, name):
        with self.lock:
            if not self.valid(identity) or not isinstance(proof, str) or len(proof) != 64 or any(c not in '0123456789abcdef' for c in proof):
                return None
            phone = self.state['phones'][identity]
            if not hmac.compare_digest(phone_proof(phone['token'], challenge, room, identity), proof):
                return None
            connection_key = session_key(phone['token'], challenge, room, identity)
            first = phone['state'] == 'pending'
            if first:
                # QR bootstrap credential becomes invalid after its first use.
                phone['token'] = secrets.token_hex(32)
                phone['state'] = 'paired'
                phone['name'] = str(name)[:64]
            phone['last_seen'] = time.time()
            self.save()
            return {'id': identity, 'token': phone['token'], 'first': first, 'session_key': connection_key}

    def phones(self):
        with self.lock:
            return [{'id': i, 'name': p['name']} for i, p in self.state['phones'].items() if p['state'] == 'paired']

    def remove(self, identity):
        with self.lock:
            self.state['phones'].pop(identity, None)
            if not self.state['phones']:
                self.state['enabled'] = False
                self.state['host'] = None
            self.save()
