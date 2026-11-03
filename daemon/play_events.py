#!/usr/bin/env python3
"""Sidecar that turns each button play into a propkit activity event (shown on the shared Dashboard).

soundtrigger.py is never touched: this only reads the log it already writes (the same file the
kiosk server follows) and records one event per play with propkit.stats.Recorder:

    PLAY: button=N file=...           -> a play starts
    PLAY_END: ... button N            -> it finished            => kind "play", outcome "ok", seconds = play time
    ERROR: aplay exited immediately   -> (in the .err.log) playback did not start => kind "play", outcome "error"
    a new PLAY while one is running   -> the first was cut off   => "ok" with interrupted=True

Only presses that actually start a play are recorded (debounced and unassigned presses never reach a PLAY line).
Runs as its own service so it cannot compete with the audio stack; the Recorder never raises.
"""
import os
import re
import signal
import sys
import time
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
_dir = os.environ.get("PROPKIT_DIR", str(Path.home() / "propkit"))
if Path(_dir).is_dir() and _dir not in sys.path:
    sys.path.insert(0, _dir)
from propkit.stats import Recorder  # noqa: E402

LOG_PATH = Path(os.environ.get("SOUNDTRIGGER_LOG", BASE_DIR / "log" / "soundtrigger.log"))
ERR_PATH = Path(os.environ.get("SOUNDTRIGGER_ERR_LOG", BASE_DIR / "log" / "soundtrigger.err.log"))   # stderr: "aplay exited immediately"
EVENTS_DIR = Path(os.environ.get("PLAY_EVENTS_DIR", BASE_DIR / "log" / "activity"))
POLL_S = 0.2
MAX_PLAY_S = 15 * 60              # a PLAY_END that never arrives is not counted as an endless play

PLAY_RE = re.compile(r"^PLAY:\s+button=(\d+)\s+file=(.*?)(?:\s+device=\S*)?\s*$")
END_RE = re.compile(r"^PLAY_END:.*button\s+(\d+)")
FAIL_RE = re.compile(r"^ERROR:\s+aplay exited immediately")

rec = Recorder(str(EVENTS_DIR))
_open = None                      # (button, track, started monotonic) of the play in progress
_stop = False


def _finish(outcome, **extra):
    global _open
    if not _open:
        return
    button, track, t0 = _open
    _open = None
    secs = time.monotonic() - t0
    if secs > MAX_PLAY_S:
        return
    rec.record("play", outcome, seconds=None if outcome == "error" else secs, detail=track, button=button, **extra)


def handle(line):
    global _open
    line = line.strip()
    m = PLAY_RE.match(line)
    if m:
        _finish("ok", interrupted=True)
        _open = (int(m.group(1)), Path(m.group(2)).stem, time.monotonic())
        return
    if END_RE.match(line):
        _finish("ok")
    elif FAIL_RE.match(line):
        _finish("error")


def main():
    global _stop
    for sig in (signal.SIGTERM, signal.SIGINT):
        signal.signal(sig, lambda *_: globals().__setitem__("_stop", True))
    paths = (LOG_PATH, ERR_PATH)
    pos = {p: (p.stat().st_size if p.exists() else 0) for p in paths}      # only plays from now on
    while not _stop:
        for path in paths:
            try:
                if not path.exists():
                    continue
                size = path.stat().st_size
                if size < pos[path]:                               # log truncated or rotated
                    pos[path] = 0
                if size > pos[path]:
                    with open(path, "r", errors="replace") as f:
                        f.seek(pos[path])
                        for line in f:
                            handle(line)
                        pos[path] = f.tell()
            except Exception as e:
                print(f"play_events: {e}", file=sys.stderr, flush=True)
        time.sleep(POLL_S)


if __name__ == "__main__":
    main()
