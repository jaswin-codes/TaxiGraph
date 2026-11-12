"""Subprocess helpers shared by the validator/OTP wrappers.

Only the spike's own child processes are started or torn down here. Windows
needs the hidden-window creation flag so a background OTP server does not
pop up a console window during automated runs.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def _creation_flags() -> int:
    if sys.platform == "win32":
        return subprocess.CREATE_NO_WINDOW
    return 0


def run_hidden(args: list[str], timeout: int | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(
        args,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
        creationflags=_creation_flags(),
    )


def popen_hidden(args: list[str], log_path: Path) -> subprocess.Popen:
    """Start a long-running child with stdout+stderr going to log_path.

    Unread PIPEs would fill up and block a chatty server such as OTP, so the
    output goes to a file instead. The child keeps its own handle open.
    """

    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("wb") as log:
        return subprocess.Popen(
            args,
            stdout=log,
            stderr=subprocess.STDOUT,
            creationflags=_creation_flags(),
        )
