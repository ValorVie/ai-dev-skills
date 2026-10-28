#!/usr/bin/env python3.14
"""Keep another account's idle process alive during the isolated cycle."""
import json
import os
import time
from pathlib import Path

if not Path('/.dockerenv').is_file() or {p.name for p in Path('/sys/class/net').iterdir()} != {'lo'}:
    raise SystemExit('offline Docker fixture required')
Path('/experiment/other-idle.json').write_text(json.dumps({'pid': os.getpid(), 'uid': os.getuid()}))
time.sleep(7200)
