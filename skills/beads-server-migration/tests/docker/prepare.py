#!/usr/bin/env python3.14
"""Create a disposable fixture inside an offline Docker container as root."""
import argparse
import json
import os
import re
import shutil
import subprocess
from pathlib import Path

if os.getuid() != 0 or not Path('/.dockerenv').is_file() or {p.name for p in Path('/sys/class/net').iterdir()} != {'lo'}:
    raise SystemExit('offline Docker root required')
parser = argparse.ArgumentParser()
parser.add_argument('--kind', choices=('fresh', 'copy'), required=True)
parser.add_argument('--uid', type=int, required=True)
parser.add_argument('--gid', type=int, required=True)
parser.add_argument('--other-uid', type=int, required=True)
parser.add_argument('--port', type=int, required=True)
parser.add_argument('--database', required=True)
parser.add_argument('--service', required=True)
args = parser.parse_args()
if not re.fullmatch(r'[A-Za-z0-9_]+', args.database) or len({args.uid, args.gid, args.other_uid, 0}) != 4:
    raise SystemExit('invalid fixture identity')
root = Path('/experiment')
if root.exists():
    raise SystemExit('fixture already exists')
subprocess.run(['groupadd', '-g', str(args.gid), 'fixturegroup'], check=True)
subprocess.run(['useradd', '-u', str(args.uid), '-g', str(args.gid), '-M', '-d', '/experiment/home', 'fixtureuser'], check=True)
subprocess.run(['useradd', '-u', str(args.other_uid), '-g', str(args.gid), '-M', '-d', '/experiment/home', 'fixtureother'], check=True)
root.mkdir(mode=0o2770)
os.chown(root, args.uid, args.gid)
os.chmod(root, 0o2770)
for name in ('home', 'migration', 'dolt-root', 'repo'):
    path = root / name
    path.mkdir(mode=0o2770)
    os.chown(path, args.uid, args.gid)
    os.chmod(path, 0o2770)
repo = root / 'repo'
env = os.environ.copy()
env.update(HOME='/experiment/home', DOLT_ROOT_PATH='/experiment/dolt-root',
           BD_DISABLE_METRICS='1', BD_DISABLE_EVENT_FLUSH='1', DOLT_DISABLE_EVENT_FLUSH='1',
           DOLT_METRICS_DISABLED='1')
def user(command, cwd=repo):
    subprocess.run(['runuser', '-u', 'fixtureuser', '--', *command], cwd=cwd, env=env, check=True)
user(['git', 'init', '-q'])
user(['git', 'init', '-q', '--bare', str(root / 'remote.git')])
if args.kind == 'copy':
    source = Path('/source')
    if not source.is_dir():
        raise SystemExit('missing read-only source')
    shutil.copytree(source, repo / '.beads', symlinks=True)
    meta = repo / '.beads/metadata.json'
    data = json.loads(meta.read_text())
    old = data['dolt_database']
    if not re.fullmatch(r'[A-Za-z0-9_]+', old):
        raise SystemExit('unexpected source database')
    tree = repo / '.beads/embeddeddolt' / old
    if any(p.name.endswith('.gate.lock') for p in tree.rglob('*')):
        raise SystemExit('database tree has gate file')
    tree.rename(tree.parent / args.database)
    data['dolt_database'] = args.database
    meta.write_text(json.dumps(data, indent=2) + '\n')
else:
    user(['bd', 'init', '--prefix', args.database, '--skip-agents', '--skip-hooks', '--non-interactive'])
    data = json.loads((repo / '.beads/metadata.json').read_text())
    if data.get('dolt_database') != args.database:
        raise SystemExit('fresh fixture database differs from requested name')
    for index in range(30):
        user(['bd', 'create', '--title', f'Fixture task {index}', '--type', 'task'])
    rows = json.loads(subprocess.run(['runuser', '-u', 'fixtureuser', '--', 'bd', '--readonly', 'list', '--all', '--limit', '1', '--json'],
                                     cwd=repo, env=env, check=True, capture_output=True, text=True).stdout)
    issue = rows[0]['id']
    user(['bd', 'comments', 'add', issue, 'fixture comment'])
    user(['bd', 'label', 'add', issue, 'fixture-label'])
beads = repo / '.beads'
if args.kind == 'fresh' and re.search(r'^sync\.remote\s*:', (beads / 'config.yaml').read_text(), re.M):
    raise SystemExit('fresh fixture unexpectedly contains sync.remote')
subprocess.run(['setfacl', '-R', '-b', '--', str(beads)], check=True)
for directory, dirs, files in os.walk(beads, followlinks=False):
    for path in [Path(directory), *(Path(directory) / n for n in dirs + files)]:
        if path.is_symlink():
            continue
        os.chown(path, args.uid, args.gid)
        os.chmod(path, 0o2770 if path.is_dir() else 0o660)
subprocess.run(['setfacl', '-R', '-m', f'g:{args.gid}:rwx', '--', str(beads)], check=True)
for directory, dirs, files in os.walk(beads, followlinks=False):
    for name in files:
        path = Path(directory) / name
        if not path.is_symlink():
            os.chmod(path, 0o660)
    subprocess.run(['setfacl', '-k', '--', directory], check=True)
    subprocess.run(['setfacl', '-m', f'd:u::rwx,d:g::rwx,d:g:{args.gid}:rwx,d:m::rwx,d:o::---', '--', directory], check=True)
    os.chmod(directory, 0o2770)
manifest = beads / 'embeddeddolt' / args.database / '.dolt/noms/manifest'
for path in (manifest, beads / 'export-state.json'):
    if path.is_file():
        subprocess.run(['setfacl', '-m', f'u::rw-,g::rwx,g:{args.gid}:rwx,m::---,o::---', '--', str(path)], check=True)
issues = beads / 'issues.jsonl'
if issues.is_file():
    subprocess.run(['setfacl', '-m', f'u::rw-,g::rwx,g:{args.gid}:rwx,m::r--,o::r--', '--', str(issues)], check=True)
acl = subprocess.run(['getfacl', '-R', '-n', '-c', '--', str(beads)], check=True, capture_output=True, text=True).stdout
named_groups = re.findall(r'^(?:default:)?group:(\d+):', acl, flags=re.M)
if any(int(group) != args.gid for group in named_groups) or re.search(r'^(?:default:)?user:\d+:', acl, flags=re.M):
    raise SystemExit('fixture retained unexpected named ACL')
os.chown(beads / 'metadata.json', args.other_uid, args.gid)
gate = repo / '.beads.gate.lock'
gate.touch(exist_ok=True)
os.chown(gate, args.uid, args.gid)
os.chmod(gate, 0o600)
config = {'hostname': os.uname().nodename.split('.')[0], 'account': 'fixtureuser',
          'repo': str(repo), 'state': str(root / 'migration'), 'port': args.port,
          'database': args.database, 'prefix': args.database, 'service': args.service,
          'group': 'fixturegroup', 'keep': 5, 'bd': '/usr/local/bin/bd',
          'dolt': '/usr/local/bin/dolt', 'docker_fixture': True}
target = root / 'target.json'
target.write_text(json.dumps(config, indent=2) + '\n')
os.chown(target, args.uid, args.gid)
os.chmod(target, 0o660)
with (root / 'unit.service').open('w') as stream:
    subprocess.run(['runuser', '-u', 'fixtureuser', '--', 'uv', 'run', '--offline', '--python', '3.14',
                    '--no-project', 'python', '-I', '-B', '/skill/scripts/render-unit.py', '--config', str(target)],
                   cwd=root, env=env, stdout=stream, check=True)
os.chown(root / 'unit.service', args.uid, args.gid)
print('disposable fixture prepared')
