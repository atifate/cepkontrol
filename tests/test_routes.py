import sys
from pathlib import Path
import unittest
import socket
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from defaults import DEFAULT_SERVER, PRIVATE_RELAY
from transport import Session
from wire import make_code
import websocket

class RouteTests(unittest.TestCase):
    def run_session(self, connections):
        _, data = make_code(DEFAULT_SERVER)
        session = Session(data, 'host', lambda *args:None)
        session.capture = lambda:None
        with patch('transport.websocket.create_connection', side_effect=connections) as connect:
            session.run()
        self.assertEqual(data['url'], DEFAULT_SERVER, 'Public QR address must remain unchanged')
        return connect.call_args_list

    def socket(self):
        connection = Mock()
        connection.recv.return_value = '{"relay":"ready"}'
        connection.recv_data.side_effect = websocket.WebSocketConnectionClosedException()
        return connection

    def test_private_route_keeps_phone_public_address(self):
        calls = self.run_session([self.socket()])
        self.assertEqual(len(calls),1)
        self.assertTrue(calls[0].args[0].startswith(PRIVATE_RELAY+'/host/'))

    def test_public_fallback_without_private_network(self):
        calls = self.run_session([OSError('Private route unavailable'),self.socket()])
        self.assertEqual(len(calls),2)
        self.assertTrue(calls[1].args[0].startswith(DEFAULT_SERVER+'/host/'))

    def test_socket_is_released_after_peer_close(self):
        _,data=make_code(DEFAULT_SERVER)
        session=Session(data,'host',lambda *args:None)
        left,right=socket.socketpair()
        connection=websocket.WebSocket()
        connection.sock=left
        connection.connected=False
        session.ws=connection
        try:
            session.close()
            self.assertIsNone(connection.sock)
            self.assertEqual(left.fileno(),-1)
        finally:
            left.close()
            right.close()

if __name__=='__main__':unittest.main()
