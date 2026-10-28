#!/usr/bin/env python3.14
"""Keep an unreadable process alive for the offline fixture."""
import ctypes
import json
import os
import time
from pathlib import Path

if not Path('/.dockerenv').is_file() or {p.name for p in Path('/sys/class/net').iterdir()} != {'lo'}:
    raise SystemExit('offline Docker fixture required')
libc = ctypes.CDLL(None, use_errno=True)
if libc.prctl(4, 0, 0, 0, 0) != 0 or libc.prctl(3, 0, 0, 0, 0) != 0:
    raise SystemExit('cannot create non-dumpable fixture')
Path('/experiment/non-dumpable.json').write_text(json.dumps({'pid': os.getpid(), 'uid': os.getuid()}))
time.sleep(7200)
