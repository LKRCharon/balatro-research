"""Long-lived, standard-library JSON-RPC client for one isolated engine.

No subprocess per action and no automatic retries. The reference Lua server
currently sends Connection: close; HTTPConnection transparently opens the next
socket, while servers supporting keep-alive reuse it. This module does not
sanitize observations or authorize actions: the environment adapter must do so.
"""
from __future__ import annotations

import argparse
import http.client
import json
import math
import sys
import threading


class TransportError(RuntimeError):
    """The action may have executed. Reconcile state; do not blindly resend."""


class ProtocolError(TransportError):
    pass


class RpcError(RuntimeError):
    def __init__(self, error, request_id, status):
        self.error, self.request_id, self.status = error, request_id, status
        super().__init__(str(error.get('message', error)))


class RpcClient:
    """Own one client per engine. Concurrent calls are serialized, never retried."""

    def __init__(self, port, *, host='127.0.0.1', timeout=30.0,
                 max_response_bytes=16 * 1024 * 1024):
        if host not in ('127.0.0.1', 'localhost', '::1'):
            raise ValueError('Only loopback engines are supported')
        if not isinstance(port, int) or isinstance(port, bool) or not 1 <= port <= 65535:
            raise ValueError('Invalid port')
        if not math.isfinite(timeout) or timeout <= 0:
            raise ValueError('Timeout must be positive and finite')
        if max_response_bytes < 1:
            raise ValueError('Response limit must be positive')
        self.host, self.port, self.timeout = host, port, timeout
        self.max_response_bytes = max_response_bytes
        self._connection = http.client.HTTPConnection(host, port, timeout=timeout)
        self._lock = threading.Lock()
        self._next_id = 1
        self._closed = False

    def call(self, method, params=None):
        if not isinstance(method, str) or not method:
            raise ValueError('Nonempty method required')
        if params is None:
            params = {}
        if not isinstance(params, dict):
            raise ValueError('params must be an object')
        with self._lock:
            if self._closed:
                raise RuntimeError('Client is closed')
            request_id = self._next_id
            self._next_id += 1
            payload = json.dumps({'jsonrpc': '2.0', 'id': request_id,
                                  'method': method, 'params': params},
                                 ensure_ascii=False, allow_nan=False).encode('utf-8')
            try:
                self._connection.request('POST', '/', payload,
                                         {'Content-Type': 'application/json'})
                response = self._connection.getresponse()
                body = response.read(self.max_response_bytes + 1)
                if len(body) > self.max_response_bytes:
                    raise ProtocolError('Response exceeds configured byte limit')
                try:
                    message = json.loads(body)
                except (ValueError, UnicodeError) as exc:
                    raise ProtocolError('Malformed JSON response') from exc
                if (not isinstance(message, dict) or message.get('jsonrpc') != '2.0'
                        or type(message.get('id')) is not int
                        or message['id'] != request_id
                        or ('result' in message) == ('error' in message)):
                    raise ProtocolError('Invalid JSON-RPC envelope or response ID')
                if 'error' in message:
                    if not isinstance(message['error'], dict):
                        raise ProtocolError('Invalid JSON-RPC error object')
                    raise RpcError(message['error'], request_id, response.status)
                if not 200 <= response.status < 300:
                    raise ProtocolError('Non-success HTTP response without RPC error')
                return message['result']
            except RpcError:
                raise
            except (OSError, http.client.HTTPException, TransportError) as exc:
                self._connection.close()
                if isinstance(exc, TransportError):
                    raise
                raise TransportError(
                    f'RPC {request_id} ({method}) failed; outcome unknown; no retry performed'
                ) from exc

    def close(self):
        with self._lock:
            self._closed = True
            self._connection.close()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()


def serve_jsonl(client, input_stream, output_stream):
    """Read {id,method,params} lines; stop on transport ambiguity (exit code 2).

    A normal RPC error is reported and processing continues. This wire utility
    is a trusted administrator interface, not the policy observation boundary.
    """
    for line in input_stream:
        request_id = None
        stop = False
        try:
            request = json.loads(line)
            if not isinstance(request, dict):
                raise ValueError('Input must be an object')
            request_id = request.get('id')
            result = client.call(request['method'], request.get('params'))
            reply = {'id': request_id, 'result': result}
        except RpcError as exc:
            reply = {'id': request_id, 'error': exc.error, 'kind': 'rpc'}
        except TransportError as exc:
            reply = {'id': request_id, 'error': str(exc), 'kind': 'transport',
                     'outcome_unknown': True}
            stop = True
        except (ValueError, KeyError, TypeError) as exc:
            reply = {'id': request_id, 'error': str(exc), 'kind': 'input'}
        output_stream.write(json.dumps(reply, ensure_ascii=False) + '\n')
        output_stream.flush()
        if stop:
            return 2
    return 0


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port', type=int, required=True,
                        help='Explicit isolated instance port; no live-backend default')
    parser.add_argument('--timeout', type=float, default=30.0)
    args = parser.parse_args()
    if hasattr(sys.stdin, 'reconfigure'):
        sys.stdin.reconfigure(encoding='utf-8')
        sys.stdout.reconfigure(encoding='utf-8')
    with RpcClient(args.port, timeout=args.timeout) as client:
        return serve_jsonl(client, sys.stdin, sys.stdout)


if __name__ == '__main__':
    raise SystemExit(main())
