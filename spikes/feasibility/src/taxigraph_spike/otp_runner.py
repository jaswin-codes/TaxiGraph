"""Wrapper around the pinned OTP 2.9.0 shaded jar: build, then load/serve.

Builds and serves on loopback only, using only the spike's own graph
directory. Does not reimplement any street/transit graph algorithm.
"""

from __future__ import annotations

import shutil
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path

from .process_utils import popen_hidden, run_hidden

GRAPHQL_PATH = "/otp/gtfs/v1"
LOOPBACK_PORT = 8080


@dataclass(frozen=True)
class BuildResult:
    status: str  # "ok" | "build_failed" | "missing_prerequisite" | "error"
    detail: str
    graph_dir: Path | None = None
    build_log: str = ""


def build_graph(
    jar_path: Path,
    gtfs_zip: Path,
    build_dir: Path,
    graph_dir: Path,
    osm_pbf: Path | None = None,
    java_binary: str = "java",
    heap: str = "-Xmx2G",
    timeout_seconds: int = 900,
) -> BuildResult:
    if not jar_path.is_file():
        return BuildResult("missing_prerequisite", f"OTP jar not found at {jar_path}")
    if not gtfs_zip.is_file():
        return BuildResult("error", f"GTFS feed not found at {gtfs_zip}")
    if osm_pbf is not None and not osm_pbf.is_file():
        return BuildResult("missing_prerequisite", f"OSM extract not found at {osm_pbf}")

    build_dir.mkdir(parents=True, exist_ok=True)
    graph_dir.mkdir(parents=True, exist_ok=True)

    # Build input dir must hold only the intended GTFS/PBF, per SOL-HANDOFF.
    # OTP's input-type sniffing keys off "gtfs" appearing in the filename
    # (a bare "feed.zip" is skipped as an unrecognized file), so the copy is
    # always renamed rather than reusing the export's own filename.
    for existing in build_dir.iterdir():
        if existing.is_file():
            existing.unlink()
    shutil.copy2(gtfs_zip, build_dir / "gtfs.zip")
    if osm_pbf is not None:
        shutil.copy2(osm_pbf, build_dir / osm_pbf.name)

    args = [
        java_binary,
        heap,
        "-jar",
        str(jar_path.resolve()),
        "--build",
        "--save",
        str(build_dir.resolve()),
    ]

    try:
        proc = run_hidden(args, timeout=timeout_seconds)
    except FileNotFoundError:
        return BuildResult("missing_prerequisite", f"{java_binary} not found")
    except subprocess.TimeoutExpired:
        return BuildResult("error", f"OTP build did not finish within {timeout_seconds}s")

    build_log = proc.stdout + proc.stderr
    built_graph = build_dir / "graph.obj"
    if proc.returncode != 0 or not built_graph.is_file():
        return BuildResult("build_failed", f"OTP build exited {proc.returncode}; no graph.obj produced", build_log=build_log)

    shutil.move(str(built_graph), str(graph_dir / "graph.obj"))
    return BuildResult("ok", "graph built", graph_dir=graph_dir, build_log=build_log)


def start_server(
    jar_path: Path,
    graph_dir: Path,
    log_path: Path,
    java_binary: str = "java",
    heap: str = "-Xmx2G",
    port: int = LOOPBACK_PORT,
) -> subprocess.Popen:
    args = [
        java_binary,
        heap,
        "-jar",
        str(jar_path.resolve()),
        "--load",
        str(graph_dir.resolve()),
        "--port",
        str(port),
    ]
    return popen_hidden(args, log_path)


def wait_for_ready(
    base_url: str,
    timeout_seconds: int = 120,
    poll_interval_seconds: float = 2.0,
    proc: subprocess.Popen | None = None,
) -> bool:
    """Poll until something is listening on base_url.

    Any HTTP response (even an error status like 404/405) proves the server
    is up; only a failure to connect at all means it isn't ready yet. If
    `proc` is given and has exited, give up at once: whatever answers on the
    port is not our server.
    """

    import urllib.error
    import urllib.request

    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        if proc is not None and proc.poll() is not None:
            return False
        try:
            with urllib.request.urlopen(base_url, timeout=5):
                return True
        except urllib.error.HTTPError:
            return True
        except (urllib.error.URLError, OSError):
            time.sleep(poll_interval_seconds)
    return False


def stop_server(proc: subprocess.Popen, timeout_seconds: int = 20) -> None:
    proc.terminate()
    try:
        proc.wait(timeout=timeout_seconds)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait(timeout=timeout_seconds)
