#!/usr/bin/env python3.14
"""Run a full cycle only on an offline, disposable Docker fixture."""
import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

root = Path('/experiment/repo')
state = Path('/experiment/migration')
config_path = Path('/experiment/target.json')
if (not Path('/.dockerenv').is_file() or Path.cwd().resolve() != root
        or {p.name for p in Path('/sys/class/net').iterdir()} != {'lo'}):
    raise SystemExit('offline Docker fixture required')
config = json.loads(config_path.read_text())
runner = ['uv', 'run', '--offline', '--python', '3.14', '--no-project', 'python', '-I', '-B']

def base(name):
    return [*runner, '/skill/scripts/' + name, '--config', str(config_path)]

def run(args, expected=0, env=None):
    start = time.monotonic()
    result = subprocess.run(args, cwd=root, env=env, capture_output=True, text=True, timeout=1200)
    print(f'{Path(args[0]).name} exit={result.returncode} elapsed={time.monotonic()-start:.1f}s', flush=True)
    if (expected == 0 and result.returncode != 0) or (expected != 0 and result.returncode == 0):
        print(result.stdout, result.stderr, file=sys.stderr)
        raise RuntimeError('unexpected command result')
    return result

def identities():
    data = json.loads(Path('/experiment/non-dumpable.json').read_text())
    proc = Path('/proc') / str(data['pid'])
    assert data['uid'] == os.getuid() == proc.stat().st_uid
    start = (proc / 'stat').read_text().rsplit(')', 1)[1].split()[19]
    try:
        list((proc / 'fd').iterdir())
    except PermissionError:
        print('same-account non-dumpable fd=PermissionError', flush=True)
    else:
        raise RuntimeError('non-dumpable process is unexpectedly readable')
    return data['pid'], start

def other_identity():
    data = json.loads(Path('/experiment/other-idle.json').read_text())
    proc = Path('/proc') / str(data['pid'])
    assert data['uid'] != os.getuid() and proc.stat().st_uid == data['uid']
    start = (proc / 'stat').read_text().rsplit(')', 1)[1].split()[19]
    try:
        list((proc / 'fd').iterdir())
    except PermissionError:
        print('other-account idle fd=PermissionError', flush=True)
    else:
        raise RuntimeError('other-account process is unexpectedly readable')
    return data['pid'], start

def metadata_identity():
    path = root / '.beads/metadata.json'
    info = path.stat()
    acl = subprocess.run(['getfacl', '-c', '-n', '-P', str(path)], capture_output=True, check=True).stdout
    return info.st_dev, info.st_ino, info.st_uid, info.st_gid, info.st_mode, acl

def check_disabled():
    active = run(['systemctl', '--user', 'is-active', config['service']], expected=1)
    enabled = run(['systemctl', '--user', 'is-enabled', config['service']], expected=1)
    assert active.stdout.strip() == 'inactive' and enabled.stdout.strip() == 'disabled'

for marker in (Path('/experiment/non-dumpable.json'), Path('/experiment/other-idle.json')):
    deadline = time.monotonic() + 30
    while not marker.is_file() and time.monotonic() < deadline:
        time.sleep(0.05)
    if not marker.is_file():
        raise RuntimeError('idle process did not report identity')
idle = identities()
other = other_identity()
metadata = metadata_identity()
run(base('switch.py'))
run([*base('switch.py'), '--apply', '--reviewed'])
assert metadata_identity() == metadata
gate = root / '.beads/dolt.gate.lock'
gate_inode = gate.stat().st_ino
run([*base('rollback.py'), '--immediate', '--apply', '--reviewed'])
check_disabled()
assert metadata_identity() == metadata and gate.stat().st_ino == gate_inode
run(['systemctl', '--user', 'enable', config['service']])
run([*base('switch.py'), '--apply', '--reviewed'])
env = os.environ.copy()
env['BEADS_DOLT_SERVER_PORT'] = str(config['port'])
rows = json.loads(run([config['bd'], '--readonly', 'list', '--all', '--limit', '1', '--json'], env=env).stdout)
issue = rows[0]['id']
run([config['bd'], '--dolt-auto-commit', 'off', 'update', issue, '--set-metadata', 'fixture_cycle=written'], env=env)
rejected = run([*base('rollback.py'), '--immediate', '--apply', '--reviewed'], expected=1)
if '伺服器資料或分支已變' not in rejected.stderr:
    raise RuntimeError('immediate rollback refusal did not prove data drift: ' + rejected.stderr)
run([*base('rollback.py'), '--after-write', '--apply', '--reviewed'])
check_disabled()
assert metadata_identity() == metadata
saved = root / '.beads/embeddeddolt.migration-saved'
saved_identity = (saved.stat().st_dev, saved.stat().st_ino)
run(base('prepare-reswitch.py'))
proc = subprocess.Popen([*runner, '/skill/tests/docker/reswitch-interrupt.py', '--config', str(config_path),
                         '--apply', '--reviewed'], cwd=root, start_new_session=True, stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE, text=True)
marker = Path('/experiment/reswitch-fault')
deadline = time.monotonic() + 1200
while time.monotonic() < deadline and proc.poll() is None and not marker.exists():
    time.sleep(0.05)
if not marker.exists() or proc.poll() is not None:
    proc.terminate()
    stdout, stderr = proc.communicate(timeout=30)
    raise RuntimeError('archive interruption not reached: ' + stdout + stderr)
os.killpg(proc.pid, signal.SIGKILL)
proc.communicate(timeout=30)
print('forced interruption after archive rename', flush=True)
run([*base('prepare-reswitch.py'), '--apply', '--reviewed'])
archives = [p / 'reswitch-saved-tree' for p in state.glob('completed-*') if (p / 'reswitch-saved-tree').is_dir()]
assert len(archives) == 1 and (archives[0].stat().st_dev, archives[0].stat().st_ino) == saved_identity
run(['systemctl', '--user', 'enable', config['service']])
run([*base('switch.py'), '--apply', '--reviewed'])
run([*base('rollback.py'), '--immediate', '--apply', '--reviewed'])
check_disabled()
assert gate.stat().st_ino == gate_inode and metadata_identity() == metadata and identities() == idle and other_identity() == other
print('full cycle passed; metadata, gate and both idle processes preserved', flush=True)
