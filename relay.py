"""Opaque, bounded two-peer WebSocket relay. Put behind Caddy for TLS."""
import asyncio
import json
import logging
import os
import re
import secrets
import time
from pathlib import Path
from websockets.http11 import Response
from websockets.datastructures import Headers
from websockets.asyncio.server import serve
from websockets.exceptions import ConnectionClosed

rooms = {}
MAX_ROOMS = int(os.environ.get('MAX_ROOMS', '100'))
MOBILE = Path(__file__).resolve().parent / 'mobile'
log = logging.getLogger('acikdestek.relay')


def http_request(connection, request):
    if request.headers.get('Upgrade', '').lower() == 'websocket':
        return None
    files = {'/': ('index.html', 'text/html; charset=utf-8'),
             '/mobile.js': ('mobile.js', 'text/javascript; charset=utf-8'),
             '/mobile.css': ('mobile.css', 'text/css; charset=utf-8'),
             '/manifest.webmanifest': ('manifest.webmanifest', 'application/manifest+json'),
             '/sw.js': ('sw.js', 'text/javascript; charset=utf-8'),
             '/icon-180.png': ('icon-180.png', 'image/png'),
             '/icon-192.png': ('icon-192.png', 'image/png'),
             '/icon-512.png': ('icon-512.png', 'image/png')}
    path = request.path.split('?', 1)[0]
    if path not in files:
        return connection.respond(404, 'Not found\n')
    name, mime = files[path]
    try:
        body = (MOBILE / name).read_bytes()
    except OSError:
        return connection.respond(503, 'Mobile client unavailable\n')
    headers = Headers({'Content-Type': mime, 'Content-Length': str(len(body)),
        'Cache-Control': 'no-store', 'X-Content-Type-Options': 'nosniff',
        'Referrer-Policy': 'no-referrer', 'X-Frame-Options': 'DENY',
        'Content-Security-Policy': "default-src 'self'; script-src 'self'; worker-src 'self'; manifest-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self' wss: ws:; frame-ancestors 'none'; base-uri 'none'; form-action 'self'"})
    return Response(200, 'OK', headers, body)


async def handler(ws):
    match = re.fullmatch(r'/(host|viewer)/([a-f0-9]{32}|[1-9][0-9]{8})', ws.request.path)
    if not match:
        await ws.close(1008, 'Invalid route')
        return
    role, room_id = match.groups()
    if role == 'host':
        if room_id in rooms or len(rooms) >= MAX_ROOMS:
            await ws.close(1008, 'Room unavailable')
            return
        room = rooms[room_id] = {'host': ws, 'viewer': None, 'tag': secrets.token_hex(4)}
    else:
        room = rooms.get(room_id)
        if not room or room['viewer'] is not None:
            await ws.close(1008, 'Host unavailable or busy')
            return
        room['viewer'] = ws
    peer_role = 'viewer' if role == 'host' else 'host'
    started = time.monotonic()
    packets = total_bytes = 0
    ending = 'peer_closed'
    received_code = sent_code = None
    log.info('connected tag=%s role=%s', room['tag'], role)
    try:
        await ws.send(json.dumps({'relay': 'ready'}))
        async with asyncio.timeout(4 * 60 * 60):
            async for packet in ws:
                if not isinstance(packet, bytes):
                    await ws.close(1008, 'Binary packets required')
                    break
                # Viewer commands never need the multi-megabyte frame allowance.
                if role == 'viewer' and len(packet) > 16384:
                    await ws.close(1009, 'Command too large')
                    break
                peer = room[peer_role]
                if peer:
                    await asyncio.wait_for(peer.send(packet), timeout=30)
                    packets += 1
                    total_bytes += len(packet)
    except ConnectionClosed as exc:
        ending = 'connection_closed'
        received_code = exc.rcvd.code if exc.rcvd else None
        sent_code = exc.sent.code if exc.sent else None
    except TimeoutError:
        ending = 'forward_timeout'
    finally:
        received_code = received_code or ws.close_code
        log.info('ended tag=%s role=%s reason=%s received=%s sent=%s seconds=%.1f packets=%s bytes=%s',
                 room['tag'], role, ending, received_code, sent_code, time.monotonic()-started, packets, total_bytes)
        # Browsers may send an empty close frame (1005) when a page is closed;
        # it must not be reported to the PC as a server/network failure.
        abnormal = ending == 'forward_timeout' or received_code not in (None, 1000, 1001, 1005)
        peer_close_code = 1011 if abnormal else 1000
        if role == 'host':
            if rooms.get(room_id) is room:
                rooms.pop(room_id, None)
            if room['viewer']:
                await room['viewer'].close(peer_close_code, 'Host connection lost' if abnormal else 'Host ended session')
        else:
            # End the room entirely: a new connection always needs a new code.
            room['viewer'] = None
            if rooms.get(room_id) is room:
                rooms.pop(room_id, None)
            await room['host'].close(peer_close_code, 'Viewer connection lost' if abnormal else 'Viewer left')


async def main():
    host = os.environ.get('RELAY_HOST', '127.0.0.1')
    port = int(os.environ.get('PORT', '8765'))
    async with serve(handler, host, port, max_size=4 * 1024 * 1024,
                     max_queue=4, compression=None, ping_interval=20, ping_timeout=60,
                     server_header=None, process_request=http_request) as server:
        print(f'AcikDestek relay listening on {host}:{port}', flush=True)
        await server.serve_forever()


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO, format='%(asctime)s %(name)s %(message)s')
    logging.getLogger('websockets.server').setLevel(logging.WARNING)
    asyncio.run(main())
