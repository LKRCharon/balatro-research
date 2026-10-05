import io
import json
import threading
import time
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from transport import ProtocolError, RpcClient, RpcError, TransportError, serve_jsonl


class FakeEngine(BaseHTTPRequestHandler):
    protocol_version = 'HTTP/1.1'

    def handle(self):
        try:
            super().handle()
        except (ConnectionResetError, ConnectionAbortedError):
            pass  # Expected when the tested client rejects an oversized reply.

    def log_message(self, *args):
        pass

    def do_POST(self):
        request = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
        self.server.requests.append((request, self.client_address))
        method = request['method']
        if method == 'timeout':
            time.sleep(0.12)
        reply = {'jsonrpc': '2.0', 'id': request['id'], 'result': request['params']}
        status = 200
        if method == 'wrong_id':
            reply['id'] += 1
        if method == 'error':
            reply.pop('result')
            reply['error'] = {'code': -32602, 'message': 'illegal action'}
            status = 400
        body = json.dumps(reply).encode()
        if method == 'malformed':
            body = b'not-json'
        if method == 'large':
            body = b' ' * 2048
        self.send_response(status)
        self.send_header('Content-Length', str(len(body)))
        if method == 'close':
            self.send_header('Connection', 'close')
            self.close_connection = True
        self.end_headers()
        try:
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
            pass


class TransportTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = ThreadingHTTPServer(('127.0.0.1', 0), FakeEngine)
        cls.server.daemon_threads = True
        cls.server.requests = []
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.port = cls.server.server_port

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join()

    def setUp(self):
        self.server.requests.clear()

    def test_reuses_connection_and_unique_ids(self):
        with RpcClient(self.port) as client:
            self.assertEqual(client.call('echo', {'reason': '同花'}), {'reason': '同花'})
            self.assertEqual(client.call('echo'), {})
        requests = self.server.requests
        self.assertEqual([r[0]['id'] for r in requests], [1, 2])
        self.assertEqual(requests[0][1], requests[1][1])

    def test_current_engine_connection_close_compatible(self):
        with RpcClient(self.port) as client:
            client.call('close')
            client.call('echo')
        self.assertEqual(len(self.server.requests), 2)
        self.assertNotEqual(self.server.requests[0][1], self.server.requests[1][1])

    def test_rpc_error_in_non_success_http_surfaces(self):
        with RpcClient(self.port) as client:
            with self.assertRaises(RpcError) as ctx:
                client.call('error')
            self.assertEqual(ctx.exception.error['code'], -32602)
            self.assertEqual(ctx.exception.status, 400)
            self.assertEqual(client.call('echo'), {})

    def test_bad_responses_are_not_retried(self):
        for method in ('wrong_id', 'malformed', 'large'):
            with self.subTest(method=method), RpcClient(self.port, max_response_bytes=1024) as client:
                before = len(self.server.requests)
                with self.assertRaises(ProtocolError):
                    client.call(method)
                self.assertEqual(len(self.server.requests), before + 1)

    def test_timeout_not_retried_and_stdio_stops(self):
        inputs = io.StringIO('{"id":"a","method":"timeout"}\n'
                            '{"id":"b","method":"echo"}\n')
        outputs = io.StringIO()
        with RpcClient(self.port, timeout=0.025) as client:
            self.assertEqual(serve_jsonl(client, inputs, outputs), 2)
        reply = json.loads(outputs.getvalue())
        self.assertTrue(reply['outcome_unknown'])
        self.assertEqual(reply['id'], 'a')
        self.assertEqual(len(self.server.requests), 1)

    def test_independent_clients_and_closed_state(self):
        a, b = RpcClient(self.port), RpcClient(self.port)
        try:
            a.call('echo')
            b.call('echo')
        finally:
            a.close()
            b.close()
        self.assertEqual([r[0]['id'] for r in self.server.requests], [1, 1])
        self.assertNotEqual(self.server.requests[0][1], self.server.requests[1][1])
        with self.assertRaises(RuntimeError):
            a.call('echo')

    def test_input_errors_never_contact_engine(self):
        output = io.StringIO()
        with RpcClient(self.port) as client:
            self.assertEqual(serve_jsonl(client, io.StringIO('[]\n{"params":{}}\n'), output), 0)
        self.assertEqual(len(self.server.requests), 0)
        self.assertEqual(len(output.getvalue().splitlines()), 2)


if __name__ == '__main__':
    unittest.main()
