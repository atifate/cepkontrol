"""Connection codes and authenticated end-to-end encryption."""
import base64
import json
import secrets
import ipaddress
import hashlib
import re
from urllib.parse import urlsplit
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from defaults import DEFAULT_SERVER


def validate_url(url):
    p = urlsplit(url)
    if p.scheme not in ('ws', 'wss') or not p.hostname or p.username or p.password or p.query or p.fragment or p.path not in ('', '/'):
        raise ValueError('Sunucu adresi wss://alan-adiniz biçiminde olmalı.')
    try:
        address = ipaddress.ip_address(p.hostname)
        local = address.is_private or (address.version == 4 and address in ipaddress.ip_network('100.64.0.0/10'))
    except ValueError:
        local = p.hostname == 'localhost'
    if p.scheme == 'ws' and not local:
        raise ValueError('Genel internet adresleri için wss:// gerekir.')
    return url.rstrip('/')


def make_code(url):
    room = str(secrets.randbelow(900000000) + 100000000)
    secret = base64.b32encode(secrets.token_bytes(16)).decode().rstrip('=')
    data = {'v': 2, 'url': validate_url(url), 'room': room,
            'key': hashlib.sha256(('AcikDestek/v2/' + secret).encode()).hexdigest()}
    code = f'AD2.{room}.{secret}'
    return code, data


def parse_code(code, url=None):
    code = code.strip()
    if re.fullmatch(r'AD2\.[1-9][0-9]{8}\.[A-Z2-7]{26}', code):
        _, room, secret = code.split('.')
        return {'v': 2, 'url': validate_url(url or DEFAULT_SERVER), 'room': room,
                'key': hashlib.sha256(('AcikDestek/v2/' + secret).encode()).hexdigest()}
    if not code.startswith('AD1.') or len(code) > 2048:
        raise ValueError('Geçerli bir CepKontrol bağlantı kodu girin.')
    try:
        data = json.loads(base64.urlsafe_b64decode(code[4:] + '=' * (-len(code[4:]) % 4)))
        if data['v'] != 1 or len(bytes.fromhex(data['room'])) != 16 or len(bytes.fromhex(data['key'])) != 32:
            raise ValueError('Invalid code')
        data['url'] = validate_url(data['url'])
        return data
    except Exception as exc:
        raise ValueError('Bağlantı kodu geçersiz veya eksik.') from exc


class Cipher:
    def __init__(self, key):
        self.aes = AESGCM(bytes.fromhex(key))

    def pack(self, data):
        nonce = secrets.token_bytes(12)
        return nonce + self.aes.encrypt(nonce, json.dumps(data, separators=(',', ':')).encode(), b'AcikDestek/v1')

    def unpack(self, data):
        if not isinstance(data, bytes) or len(data) < 28:
            raise ValueError('Geçersiz paket')
        message = json.loads(self.aes.decrypt(data[:12], data[12:], b'AcikDestek/v1'))
        if not isinstance(message, dict):
            raise ValueError('Geçersiz mesaj')
        return message
