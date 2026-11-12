import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

from taxigraph_spike import otp_runner, process_utils


class _NotFound(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_error(404)

    def log_message(self, *args):
        pass


def test_popen_hidden_logs_output_without_blocking(tmp_path: Path):
    log_path = tmp_path / "logs" / "server.log"
    # Far more than a pipe buffer holds; a child writing this to an unread PIPE would hang.
    code = "import sys; sys.stdout.write('x' * 500000); sys.stderr.write('err')"

    proc = process_utils.popen_hidden([sys.executable, "-c", code], log_path)

    assert proc.wait(timeout=30) == 0
    content = log_path.read_bytes()
    assert content.count(b"x") == 500000
    assert b"err" in content


def test_wait_for_ready_true_on_http_error_status():
    server = HTTPServer(("127.0.0.1", 0), _NotFound)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        assert otp_runner.wait_for_ready(f"http://127.0.0.1:{server.server_port}", timeout_seconds=10)
    finally:
        server.shutdown()
        server.server_close()


def test_wait_for_ready_gives_up_when_process_has_exited(tmp_path: Path):
    proc = process_utils.popen_hidden([sys.executable, "-c", "pass"], tmp_path / "exited.log")
    proc.wait(timeout=30)

    started = time.monotonic()
    ready = otp_runner.wait_for_ready("http://127.0.0.1:9", timeout_seconds=60, poll_interval_seconds=0.1, proc=proc)

    assert ready is False
    assert time.monotonic() - started < 5


def test_build_graph_missing_jar_is_missing_prerequisite(tmp_path: Path):
    result = otp_runner.build_graph(tmp_path / "nope.jar", tmp_path / "gtfs.zip", tmp_path / "b", tmp_path / "g")
    assert result.status == "missing_prerequisite"
