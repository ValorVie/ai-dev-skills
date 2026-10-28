#!/usr/bin/env python3
"""Run two disposable, network-isolated migration cycles; preview by default."""
import argparse
import json
import subprocess
import sys
import uuid
from pathlib import Path

parser = argparse.ArgumentParser()
parser.add_argument('--image', required=True, help='already-built local test image')
parser.add_argument('--source', required=True, type=Path, help='existing embedded .beads copy')
parser.add_argument('--logs', required=True, type=Path, help='existing empty evidence directory')
parser.add_argument('--apply', action='store_true')
parser.add_argument('--reviewed', action='store_true')
args = parser.parse_args()
if args.apply != args.reviewed:
    raise SystemExit('需要同時指定 --apply --reviewed')
skill = Path(__file__).resolve().parents[2]
source = args.source.resolve(strict=True)
logs = args.logs.resolve(strict=True)
if not source.is_dir() or '.beads' in source.parts or not logs.is_dir() or any(logs.iterdir()):
    raise SystemExit('source 須為目錄，logs 須為空目錄')
if any(',' in str(path) or '\n' in str(path) for path in (skill, source)):
    raise SystemExit('Docker bind 路徑不得含逗號或換行')
cases = [('fresh', 12101, 12102, 12103, 16421, 'samplefresh', 'samplefresh.service'),
         ('copy', 12201, 12202, 12203, 16422, 'archivecopy', 'archivecopy.service')]
print('預覽：兩個 --network none、--cpus 4 的容器；不修改來源副本。')
print(f'來源={source} 證據={logs} 映像={args.image}')
print('成功後列出並刪除本工具建立的容器；失敗時保留容器及證據供檢查。')
if not args.apply:
    raise SystemExit(0)

subprocess.run(['docker', 'image', 'inspect', args.image], check=True, stdout=subprocess.DEVNULL)
names = []
for kind, uid, gid, other, port, database, service in cases:
    name = 'beads-migration-' + uuid.uuid4().hex[:12]
    names.append(name)
    print(f'{kind} 容器={name}', flush=True)
    command = ['docker', 'create', '--pull', 'never', '--init', '--network', 'none', '--cpus', '4', '--name', name,
               '--user', '0', '--env', 'PATH=/skill/tests/docker:/app/.venv/bin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin',
               '--mount', f'type=bind,src={skill},dst=/skill,readonly']
    if kind == 'copy':
        command += ['--mount', f'type=bind,src={source},dst=/source,readonly']
    command += ['--entrypoint', '/bin/sleep', args.image, '7200']
    subprocess.run(command, check=True, stdout=subprocess.DEVNULL)
    subprocess.run(['docker', 'start', name], check=True, stdout=subprocess.DEVNULL)
    raw = subprocess.run(['docker', 'inspect', name], check=True, capture_output=True, text=True).stdout
    info = json.loads(raw)[0]
    mounts = {m['Destination']: m for m in info['Mounts']}
    if (info['HostConfig']['NetworkMode'] != 'none' or info['HostConfig']['NanoCpus'] != 4_000_000_000
            or not info['HostConfig'].get('Init') or mounts['/skill']['RW']
            or (kind == 'copy' and (mounts['/source']['RW'] or mounts['/source']['Source'] != str(source)))):
        raise RuntimeError('container isolation mismatch')
    with (logs / (kind + '-container.json')).open('x') as output:
        json.dump({'name': name, 'image_id': info['Image'], 'network': 'none', 'cpus': 4,
                   'init': True, 'skill_readonly': True, 'source_readonly': kind == 'copy'}, output, indent=2)
        output.write('\n')
    with (logs / (kind + '-prepare.log')).open('x') as output:
        subprocess.run(['docker', 'exec', name, 'uv', 'run', '--offline', '--python', '3.14', '--no-project', 'python', '-I', '-B', '/skill/tests/docker/prepare.py',
                        '--kind', kind, '--uid', str(uid), '--gid', str(gid), '--other-uid', str(other),
                        '--port', str(port), '--database', database, '--service', service],
                       check=True, stdout=output, stderr=subprocess.STDOUT, timeout=1200)
    for who, script in ((uid, 'non-dumpable.py'), (other, 'other-idle.py')):
        subprocess.run(['docker', 'exec', '-d', '-u', f'{who}:{gid}', '-e', 'HOME=/experiment/home',
                        '-e', f'UV_CACHE_DIR=/experiment/uv-cache-{who}', name,
                        'uv', 'run', '--offline', '--python', '3.14', '--no-project', 'python', '-I', '-B',
                        '/skill/tests/docker/' + script], check=True)
    with (logs / (kind + '-cycle.log')).open('x') as output:
        subprocess.run(['docker', 'exec', '-u', f'{uid}:{gid}', '-w', '/experiment/repo',
                        '-e', 'HOME=/experiment/home', '-e', 'UV_OFFLINE=1', '-e', 'DOLT_ROOT_PATH=/experiment/dolt-root',
                        name, 'uv', 'run', '--offline', '--python', '3.14', '--no-project', 'python', '-I', '-B', '/skill/tests/docker/cycle.py'],
                       check=True, stdout=output, stderr=subprocess.STDOUT, timeout=7200)
    print(kind + ' cycle passed', flush=True)
for name in names:
    subprocess.run(['docker', 'stop', name], check=True)
    subprocess.run(['docker', 'ps', '-a', '--filter', 'name=^/' + name + '$', '--format', '{{.Names}} {{.Status}}'], check=True)
    subprocess.run(['docker', 'rm', name], check=True)
print('兩個循環通過；測試容器已列出並刪除')
