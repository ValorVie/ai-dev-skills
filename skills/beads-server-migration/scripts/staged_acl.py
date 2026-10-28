"""Reconcile common-path ACLs before moving a restored tree into Beads."""
import os
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import permissions


def apply(path, entry, protected):
    if path.is_symlink() or entry['kind'] not in ('file', 'dir'):
        raise ValueError(f'unsupported staging path: {path}')
    resolved = path.resolve(strict=True)
    protected = Path(protected).resolve(strict=False)
    if resolved == protected or protected in resolved.parents:
        raise ValueError('ACL changes are forbidden inside Beads')
    subprocess.run(['setfacl', '--set-file=-', '--', str(path)], input=entry['acl'],
                   text=True, capture_output=True, check=True)
    os.chmod(path, entry['mode'], follow_symlinks=False)


def reconcile(stage, baseline, protected):
    stage = Path(stage)
    protected = Path(protected).resolve(strict=False)
    if stage.is_symlink() or not stage.is_dir():
        raise ValueError('invalid staging directory')
    resolved = stage.resolve(strict=True)
    if resolved == protected or protected in resolved.parents:
        raise ValueError('staging must be outside the protected Beads directory')
    current = permissions.capture(resolved)
    for rel in sorted(current.keys() & baseline.keys()):
        path = resolved if rel == '.' else resolved / rel
        if current[rel]['kind'] != baseline[rel]['kind']:
            raise ValueError(f'staging type changed: {rel}')
        apply(path, baseline[rel], protected)
    after = permissions.capture(resolved)
    for rel in current.keys() & baseline.keys():
        if any(after[rel][key] != baseline[rel][key] for key in ('kind', 'mode', 'acl')):
            raise ValueError(f'staging permissions differ: {rel}')
