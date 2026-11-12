import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from taxigraph_spike import graphql_client


def _serve(body: bytes):
    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            self.send_response(200)
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args):
            pass

    server = HTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server


@pytest.mark.parametrize(
    ("body", "status"),
    [
        (json.dumps({"data": {"x": 1}}).encode(), "ok"),
        (json.dumps({"data": None, "errors": [{"message": "bad"}]}).encode(), "graphql_error"),
        (b"<html>not json</html>", "graphql_error"),
        (b"\xff\xfe", "graphql_error"),
        (b"[]", "graphql_error"),
    ],
)
def test_post_query_statuses(body, status):
    server = _serve(body)
    try:
        result = graphql_client.post_query(f"http://127.0.0.1:{server.server_port}", "query { x }")
    finally:
        server.shutdown()
        server.server_close()
    assert result.status == status


def test_unreachable_server_is_otp_unavailable():
    # Port 9 (discard) is not listening on loopback in normal setups.
    result = graphql_client.post_query("http://127.0.0.1:9", "query { x }", timeout_seconds=2)
    assert result.status == "otp_unavailable"
