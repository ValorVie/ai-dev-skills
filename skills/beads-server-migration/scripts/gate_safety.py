"""Do not delete an inactive record if it still contains a gate file."""
import os
from pathlib import Path


def contains_gate(root):
    def walk_error(error):
        raise error
    for directory, dirs, files in os.walk(root, followlinks=False, onerror=walk_error):
        if any(name.endswith('.gate.lock') for name in dirs + files):
            return True
    return Path(root).name.endswith('.gate.lock')
