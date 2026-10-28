#!/usr/bin/env python3
"""Prepare and switch a stopped Beads workspace to a local Dolt server."""
import argparse
import contextlib
import datetime
import fcntl
import json
import os
import pwd
import re
import shutil
import socket
import stat
import subprocess
import sys
import time
import uuid
import shlex
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from metadata_io import sha, write_in_place
import retention
import state_retention
import gate_safety
import target_config

TOOLS = Path(__file__).resolve().parent
SERVICE = None
CONFIG = None
SAVED = "embeddeddolt.migration-saved"
LOG_PATH = None


def configure(path):
    global CONFIG, SERVICE
    CONFIG = target_config.load(path)
    SERVICE = CONFIG['service']


def config_digest():
    return sha(json.dumps(CONFIG, sort_keys=True, separators=(',', ':')).encode())


def check_target_config(target):
    if (any(type(target.get(key)) is not int for key in ('port', 'uid', 'keep'))
            or target.get('config_sha256') != config_digest()
            or target.get('repo') != CONFIG['repo'] or target.get('port') != CONFIG['port']
            or target.get('uid') != os.getuid() or target.get('keep') != CONFIG['keep']):
        raise ValueError('設定與切換檢查點不符')


BD_SELECTOR_ENV = (
    'BEADS_DIR', 'BEADS_DB', 'BD_DB', 'BEADS_DOLT_SERVER_DATABASE', 'BEADS_DOLT_SERVER_HOST',
    'BEADS_DOLT_SERVER_PORT', 'BEADS_DOLT_PORT', 'BEADS_DOLT_SERVER_SOCKET', 'BEADS_DOLT_SERVER_MODE',
    'BEADS_DOLT_SHARED_SERVER', 'BEADS_DOLT_PROXIED_SERVER', 'BEADS_DOLT_DATA_DIR',
    'BEADS_SHARED_SERVER_DIR', 'BEADS_CENTRAL_CONFIG', 'BEADS_PROXIED_SERVER_CONFIG',
    'BEADS_PROXIED_SERVER_ROOT_PATH', 'BD_BACKEND', 'BD_DATABASE_BACKEND', 'BD_DOLT_HOST',
    'BD_DOLT_PORT', 'BD_DOLT_SHARED_SERVER', 'BD_DOLT_DATA_DIR', 'BD_DOLT_DATABASE', 'BD_DOLT_MODE',
    'BD_DOLT_SERVER_HOST', 'BD_DOLT_SERVER_PORT', 'BD_DOLT_SERVER_SOCKET', 'BD_DOLT_SOCKET',
    'BD_DOLT_PROXIED_SERVER', 'BEADS_DOLT_AUTO_START', 'BEADS_DOLT_CREDENTIAL_COMMAND',
    'BEADS_PRODUCTION_PORT', 'BEADS_SKIP_IDENTITY_CHECK', 'BEADS_TEST_MODE', 'BEADS_TEST_SERVER',
    'BD_SYNC_REMOTE', 'BD_SYNC_GIT_REMOTE', 'BEADS_TEST_IGNORE_REPO_CONFIG',
    'BD_NO_DB', 'BEADS_NO_DB',
    'BD_DATABASE', 'BEADS_DATABASE', 'BEADS_BACKEND', 'BEADS_DATABASE_BACKEND',
    'BD_BACKUP_ENABLED', 'BEADS_BACKUP_ENABLED', 'BD_BACKUP_GIT_REPO', 'BEADS_BACKUP_GIT_REPO',
    *(prefix + key for prefix in ('BD_', 'BEADS_') for key in
      ('ROUTING_MODE', 'ROUTING_DEFAULT', 'ROUTING_MAINTAINER', 'ROUTING_CONTRIBUTOR',
       'CONTRIBUTOR_AUTO_ROUTE', 'CONTRIBUTOR_PLANNING_REPO')),
)
BD_SELECTOR_PREFIXES = tuple(prefix + root + '_' for prefix in ('BD_', 'BEADS_')
                             for root in ('DOLT',))
BD_SELECTOR_ROOTS = tuple(prefix[:-1] for prefix in BD_SELECTOR_PREFIXES)
SAFE_SELECTOR_ENV = frozenset({'BD_DOLT_MAX_CONNS', 'BEADS_DOLT_MAX_CONNS'})

# Beads 1.3.1 internal/storage/dolt/open.go:318-332: connection pool size only.
DOLT_SAFE_KEYS = frozenset({'dolt.max-conns'})
UNSAFE_CONFIG_ROOTS = frozenset({'db', 'no-db'})
UNSAFE_CONFIG_KEYS = frozenset({'backup.enabled', 'backup.git-repo', 'routing.mode', 'routing.default',
                                'routing.maintainer', 'routing.contributor', 'contributor.auto_route',
                                'contributor.planning_repo'})


def isolate_sync_remote(text, remote, user_config=False, guard=False):
    """Accept only simple YAML mappings so an alternate sync key cannot hide."""
    message = 'config.yaml 格式不支援；請整理為簡單鍵值設定，移除頂層 sync 區塊並保留至多一行 sync.remote'
    lines = text.splitlines(keepends=True)
    keys = {}
    dotted_keys = set()
    stack = []
    remote_line = None
    dolt_container = False
    dolt_value_seen = False
    for index, line in enumerate(lines):
        if not line.strip() or line.lstrip().startswith('#'):
            continue
        match = re.fullmatch(r'( *)([A-Za-z0-9_.-]+):(?:[ ]+(.*?))?[ ]*\r?\n?', line)
        if not match:
            raise ValueError(message)
        indent, key, value = len(match[1]), match[2].lower(), match[3] or ''
        while stack and stack[-1][0] >= indent:
            stack.pop()
        if indent and (not stack or not stack[-1][2]):
            raise ValueError(message)
        if not indent and key == 'db':
            raise ValueError('設定含頂層 db 鍵；請移除選庫設定後重新預覽')
        if not user_config and not indent and key == 'sync':
            raise ValueError(message)
        path = tuple(item[1] for item in stack) + (key,)
        if path in keys:
            raise ValueError(message)
        keys[path] = True
        # Restrict values to single-line scalars; reject aliases, flow collections,
        # block strings and quoted keys instead of guessing their YAML meaning.
        value = re.split(r'\s+#', value, maxsplit=1)[0].strip()
        dotted = '.'.join(path)
        if guard:
            if dotted in dotted_keys:
                raise ValueError(message)
            dotted_keys.add(dotted)
            root = dotted.split('.')[0]
            if root in UNSAFE_CONFIG_ROOTS or dotted in UNSAFE_CONFIG_KEYS:
                raise ValueError('config.yaml 含不支援的選庫、連線或推送鍵；請移除後重新預覽')
            if root == 'dolt':
                if dotted == 'dolt' and not value and len(path) == 1:
                    dolt_container = True
                elif dotted in DOLT_SAFE_KEYS and value:
                    if len(path) > 1 and path[0] == 'dolt':
                        dolt_value_seen = True
                else:
                    raise ValueError('config.yaml 的 dolt 設定不在白名單；請移除後重新預覽')
        if value and not (re.fullmatch(r'"(?:[^"\\]|\\["\\/bfnrt]|\\u[0-9a-fA-F]{4})*"', value)
                          or re.fullmatch(r"'(?:[^']|'')*'", value)
                          or (not re.search(r"[\[\]{}'\"&*!|>%@`]|:\s", value)
                              and not value.startswith(('-', '?', ':', '#')))):
            raise ValueError(message)
        if not user_config and not indent and key == 'sync.remote' and value.lower() in ('', 'null', '~', '""', "''"):
            raise ValueError(message)
        stack.append((indent, key, not value))
        if not indent and key == 'sync.remote':
            remote_line = index
    if guard and dolt_container and not dolt_value_seen:
        raise ValueError('config.yaml 的 dolt 設定不在白名單；請移除後重新預覽')
    if user_config:
        return text
    replacement = 'sync.remote: ' + json.dumps(remote) + '\n'
    if remote_line is None:
        if text and not text.endswith('\n'):
            lines.append('\n')
        lines.append(replacement)
    else:
        lines[remote_line] = replacement
    return ''.join(lines)


def reject_selector_environment():
    names = sorted(name for name in os.environ if name not in SAFE_SELECTOR_ENV and
                   (name in BD_SELECTOR_ENV or name in BD_SELECTOR_ROOTS or name.startswith(BD_SELECTOR_PREFIXES)))
    if names:
        raise RuntimeError('已設定選庫或測試環境變數：' + ', '.join(names))


def reject_workspace_overrides(beads, env=None):
    scratch_remote = None
    if (CONFIG and CONFIG.get('state') and beads.parent.name == 'backup-repo'
            and beads.parent.parent.parent == Path(CONFIG['state'])):
        state = Path(CONFIG['state'])
        work = state / 'current'
        if beads.parent != scratch_root(state, work) / 'backup-repo':
            raise ValueError('暫存工作區與檢查點不符')
        scratch_remote = (work / 'remote.git').as_uri()
        if (beads / 'config.yaml').is_symlink() or not (beads / 'config.yaml').is_file():
            raise ValueError('scratch 設定檔不可用')
    for name in ('.env', 'redirect', 'config.local.yaml'):
        path = beads / name
        try:
            path.lstat()
        except FileNotFoundError:
            continue
        except OSError as error:
            raise RuntimeError('無法檢查工作區設定；請確認讀取權限後重新預覽') from error
        raise RuntimeError('工作區含可能改變選庫的檔案：' + name + '；請移除或整理後重新預覽')
    env = os.environ if env is None else env
    home = env.get('HOME', '')
    native = env.get('XDG_CONFIG_HOME') or str(Path(home) / '.config')
    if not Path(home).is_absolute() or not Path(native).is_absolute():
        raise ValueError('使用者設定目錄不明；請確認 HOME 與 XDG_CONFIG_HOME 後重新預覽')
    paths = (beads / 'config.yaml', Path(home) / '.beads/config.yaml',
             Path(native) / 'bd/config.yaml', Path(home) / '.config/bd/config.yaml')
    for path in dict.fromkeys(paths):
        try:
            path.lstat()
        except FileNotFoundError:
            continue
        except OSError as error:
            raise RuntimeError('無法檢查設定檔；請確認讀取權限後重新預覽') from error
        try:
            text = path.read_bytes().decode('utf-8')
        except (OSError, UnicodeError) as error:
            raise RuntimeError('無法讀取設定檔；請確認讀取權限及格式後重新預覽') from error
        project = path == beads / 'config.yaml'
        isolate_sync_remote(text, 'file:///local-placeholder', user_config=not project, guard=True)
        if project and scratch_remote is not None and text != isolate_sync_remote(text, scratch_remote):
            raise ValueError('scratch 遠端與受控本機遠端不符')


def child_environment(env):
    source = dict(os.environ if env is None else env)
    # Only an explicit tool-created environment may supply the fixed local port.
    port = source.get('BEADS_DOLT_SERVER_PORT') if env is not None else None
    for name in tuple(source):
        if name not in SAFE_SELECTOR_ENV and (name in BD_SELECTOR_ENV or name in BD_SELECTOR_ROOTS
                                               or name.startswith(BD_SELECTOR_PREFIXES)):
            source.pop(name)
    if port is not None:
        if port != str(CONFIG['port']):
            raise ValueError('內部伺服器通訊埠不符')
        source['BEADS_DOLT_SERVER_PORT'] = port
    return source


def verify_bd_workspace(cwd, env, allow_init=False):
    if cwd is None:
        raise ValueError('bd 子程序缺少工作區')
    beads = Path(cwd) / '.beads'
    reject_workspace_overrides(beads, env)
    if beads.is_symlink():
        raise ValueError('bd 工作區不可為符號連結')
    if not beads.exists():
        if allow_init:
            return
        raise ValueError('bd 工作區不存在')
    metadata = beads / 'metadata.json'
    if metadata.is_symlink() or not metadata.is_file():
        raise ValueError('bd 工作區 metadata 不可用')
    config = json.loads(metadata.read_bytes())
    port = env.get('BEADS_DOLT_SERVER_PORT')
    if config.get('dolt_database') != CONFIG['database']:
        raise ValueError('bd 工作區資料庫不符')
    if port is None and config.get('dolt_mode') != 'embedded':
        raise ValueError('bd 工作區不是 embedded')
    if port is not None and (config.get('dolt_mode') != 'server'
                             or config.get('dolt_server_host') != '127.0.0.1'
                             or config.get('dolt_server_port') != int(port)):
        raise ValueError('bd 伺服器工作區不符')


def execution_allowed(repo):
    return target_config.execution_allowed(CONFIG, repo)


def log_event(message):
    if LOG_PATH is None:
        return
    with LOG_PATH.open('a', encoding='utf-8') as stream:
        stream.write(datetime.datetime.now(datetime.UTC).isoformat() + ' ' + message + '\n')
        stream.flush()
        os.fsync(stream.fileno())


def run(args, cwd=None, env=None):
    env = child_environment(env)
    args = list(args)
    if args[0] in ('bd', 'dolt'):
        args[0] = CONFIG[args[0]]
    if args[0] == CONFIG['bd']:
        initializing = len(args) > 1 and args[1] == 'init'
        verify_bd_workspace(cwd, env, allow_init=initializing)
        if initializing:
            state = Path(CONFIG['state'])
            work = state / 'current'
            remote = work / 'remote.git'
            if Path(cwd) != scratch_root(state, work) / 'server-repo' or remote.is_symlink() or not remote.is_dir():
                raise ValueError('初始化工作區或本機遠端不符')
            env['BD_SYNC_REMOTE'] = remote.as_uri()
        env['BEADS_DIR'] = str(Path(cwd).resolve() / '.beads')
        env.update(BD_ROUTING_MODE='explicit', BD_ROUTING_DEFAULT='.', BD_EXPORT_AUTO='false')
    log_event('開始 ' + Path(args[0]).name)
    env['DOLT_DISABLE_EVENT_FLUSH'] = '1'
    env['DOLT_METRICS_DISABLED'] = '1'
    env['BD_DISABLE_METRICS'] = '1'
    env['BD_DISABLE_EVENT_FLUSH'] = '1'
    proc = subprocess.run(args, cwd=cwd, env=env, capture_output=True, text=True, timeout=600)
    log_event('結束 ' + Path(args[0]).name + ' exit=' + str(proc.returncode))
    if proc.returncode:
        raise RuntimeError(f"{Path(args[0]).name} 失敗，退出碼 {proc.returncode}")
    return proc.stdout


def verify_scratch_location(scratch, env):
    location = json.loads(run(['bd', 'where', '--json'], scratch, env))
    if (Path(location.get('path', '')).resolve() != (scratch / '.beads').resolve()
            or Path(location.get('database_path', '')).resolve() != (scratch / '.beads/embeddeddolt').resolve()):
        raise RuntimeError('bd 讀回的工作區或資料庫路徑與暫存副本不符；停止')


def normalize_init_remote(stage, remote):
    path = stage / '.beads/config.yaml'
    if path.is_symlink() or not path.is_file():
        raise ValueError('初始化設定檔不可用')
    text = path.read_text(encoding='utf-8')
    block = '\nsync:\n    remote: ' + json.dumps(remote) + '\n'
    if text.count(block) != 1:
        raise ValueError('初始化產生的遠端設定不符')
    path.write_text(isolate_sync_remote(text.replace(block, '\n', 1), remote, guard=True), encoding='utf-8')


def no_bd():
    for path in Path('/proc').glob('[0-9]*/comm'):
        try:
            name = path.read_text().strip()
            if name == 'bd' or name.startswith('bd-'):
                raise RuntimeError(f"仍有 bd 程序：{path.parent.name}")
        except FileNotFoundError:
            continue


@contextlib.contextmanager
def workspace_gate(repo):
    fd = os.open(repo / '.beads.gate.lock', os.O_RDWR | os.O_NOFOLLOW)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        no_bd()
        yield
    finally:
        os.close(fd)


def durable(path, data):
    with path.open('xb') as stream:
        stream.write(data)
        stream.flush()
        os.fsync(stream.fileno())
    fd = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def validate_state(state, beads):
    if state.is_symlink() or not state.is_dir():
        raise ValueError('須先建立狀態目錄')
    info = state.stat()
    if (info.st_dev != beads.stat().st_dev or info.st_uid != os.getuid()
            or info.st_gid != target_config.group_id(CONFIG) or stat.S_IMODE(info.st_mode) != 0o2770):
        raise ValueError('狀態目錄須在同一檔案系統，owner 為執行者、設定的群組、模式 2770')


def scratch_root(state, work):
    pointer = work / 'scratch-id'
    if pointer.is_symlink() or not pointer.is_file():
        raise ValueError('缺少 scratch 位置紀錄')
    name = pointer.read_text().strip()
    if not re.fullmatch(r'migration-scratch-[0-9a-f]{32}', name):
        raise ValueError('scratch 名稱不符')
    root = state / name
    if root.is_symlink() or not root.is_dir() or root.resolve() != root:
        raise ValueError('scratch 目錄不符')
    info = root.stat()
    marker, target, source = root / '.migration-scratch', root / 'target.json', work / 'target.json'
    if (info.st_uid != os.getuid() or info.st_gid != target_config.group_id(CONFIG) or info.st_dev != state.stat().st_dev
            or stat.S_IMODE(info.st_mode) != 0o2770
            or marker.is_symlink() or not marker.is_file() or marker.read_bytes() != b'migration-scratch-v1\n'
            or target.is_symlink() or not target.is_file() or source.is_symlink() or not source.is_file()
            or target.read_bytes() != source.read_bytes()):
        raise ValueError('scratch 身分或目標不符')
    return root


def helper(name, args, cwd, env=None):
    env = child_environment(env)
    if name == 'snapshot.py':
        verify_bd_workspace(cwd, env)
        env['BEADS_DIR'] = str(Path(cwd).resolve() / '.beads')
        env.update(BD_ROUTING_MODE='explicit', BD_ROUTING_DEFAULT='.', BD_EXPORT_AUTO='false')
    log_event('開始 ' + name)
    env['DOLT_DISABLE_EVENT_FLUSH'] = '1'
    env['DOLT_METRICS_DISABLED'] = '1'
    env['BD_DISABLE_METRICS'] = '1'
    env['BD_DISABLE_EVENT_FLUSH'] = '1'
    args = list(args)
    if name == 'permissions.py' and '--group' not in args:
        args += ['--group', target_config.group_id(CONFIG)]
    elif name == 'db-fingerprint.py':
        args += ['--dolt', CONFIG['dolt']]
    elif name == 'snapshot.py':
        index = args.index('--bd') + 1
        args[index] = CONFIG['bd']
    command = [sys.executable, str(TOOLS / name), *map(str, args)]
    proc = subprocess.run(command, cwd=cwd, env=env, capture_output=True, text=True, timeout=600)
    log_event('結束 ' + name + ' exit=' + str(proc.returncode))
    if proc.returncode:
        if proc.stderr:
            print(proc.stderr, file=sys.stderr, end='')
        raise RuntimeError(f'{name} 失敗，退出碼 {proc.returncode}')
    return proc.stdout


def require_same_fingerprint(expected, actual):
    if expected != actual:
        raise RuntimeError('完整資料指紋不一致')


def ensure_tree_idle(path, allowed_pids=()):
    tool = shutil.which('fuser') or shutil.which('lsof')
    if not tool or not state_retention.inspectable():
        raise RuntimeError('無法確認資料樹是否被使用')
    if not state_retention.no_mounts(path) or state_retention.in_use(tool, path, allowed_pids):
        raise RuntimeError('資料樹仍在使用')


def ready(port):
    for _ in range(60):
        with socket.socket() as sock:
            sock.settimeout(0.2)
            if sock.connect_ex(('127.0.0.1', port)) == 0:
                return
        time.sleep(0.5)
    raise RuntimeError('Dolt 伺服器未就緒')


def verify_server(beads, port):
    pid_text = run(['systemctl', '--user', 'show', '--property=MainPID', '--value', SERVICE]).strip()
    if not pid_text.isdigit() or int(pid_text) <= 0:
        raise RuntimeError('服務 PID 不明')
    proc = Path('/proc') / pid_text
    if proc.stat().st_uid != os.getuid():
        raise RuntimeError('服務帳號不符')
    args = proc.joinpath('cmdline').read_bytes().split(b'\0')
    required = [b'sql-server', b'--host', b'127.0.0.1', b'--port', str(port).encode(),
                b'--data-dir', os.fsencode(beads / 'dolt')]
    if any(value not in args for value in required):
        raise RuntimeError('服務程序與目標不符')
    inodes = set()
    for line in Path('/proc/net/tcp').read_text().splitlines()[1:]:
        fields = line.split()
        if fields[1] == f'0100007F:{port:04X}' and fields[3] == '0A':
            inodes.add(fields[9])
    descriptors = set()
    for entry in (proc / 'fd').iterdir():
        try:
            target = os.readlink(entry)
        except FileNotFoundError:
            continue
        if target.startswith('socket:[') and target.endswith(']'):
            descriptors.add(target[8:-1])
    if not inodes.intersection(descriptors):
        raise RuntimeError('服務程序未持有指定監聽通訊埠')
    return int(pid_text)


def main():
    global LOG_PATH
    parser = argparse.ArgumentParser()
    parser.add_argument('--config', type=Path, required=True)
    parser.add_argument('--apply', action='store_true')
    parser.add_argument('--reviewed', action='store_true')
    args = parser.parse_args()
    configure(args.config)
    args.repo, args.state = Path(CONFIG['repo']), Path(CONFIG['state'])
    args.port, args.keep = CONFIG['port'], CONFIG['keep']
    if args.apply != args.reviewed:
        raise ValueError('需要同時指定 --apply --reviewed')
    reject_selector_environment()
    repo = args.repo.resolve(strict=True)
    if args.apply and not execution_allowed(repo):
        raise RuntimeError('套用目標不是指定離線容器或設定宣告的主機與帳號')
    beads = repo / '.beads'
    reject_workspace_overrides(beads)
    state = args.state.absolute()
    if (beads.is_symlink() or not beads.is_dir() or state != state.resolve(strict=False) or '.cache' in state.parts
            or state == beads or beads in state.parents):
        raise ValueError('無效目標或狀態目錄')
    if beads.stat().st_uid != os.getuid() or args.port != CONFIG['port'] or args.keep < 1:
        raise ValueError('執行帳號或通訊埠不符')
    metadata = beads / 'metadata.json'
    if metadata.is_symlink() or not metadata.is_file() or not target_config.executables_ok(CONFIG):
        raise ValueError('metadata 或 bd 不可用')
    original = metadata.read_bytes()
    config = json.loads(original)
    if config.get('dolt_database') != CONFIG['database'] or not config.get('project_id'):
        raise ValueError('目標不是設定的資料庫')
    visible = state_retention.inspectable()
    print('退回程序可見性：' + ('通過' if visible else '未通過；不得套用'))
    if args.apply and not visible:
        raise RuntimeError('無法確認退回所需程序可見性')
    if config.get('dolt_mode') == 'server':
        work = state / 'current'
        target = json.loads((work / 'target.json').read_text())
        check_target_config(target)
        if (not (work / 'switch-complete').is_file() or not (beads / SAVED).is_dir()
                or target['repo'] != str(repo) or target['uid'] != os.getuid()
                or target['project_id'] != config['project_id'] or config.get('dolt_server_host') != '127.0.0.1'
                or config.get('dolt_server_port') != args.port):
            raise RuntimeError('伺服器模式與保留紀錄不一致')
        verify_server(beads, args.port)
        print('已切換且服務身分符合；不異動')
        return 0
    if config.get('dolt_mode') != 'embedded':
        raise ValueError('目標不是設定的 embedded 資料庫')
    source_config = beads / 'config.yaml'
    if source_config.is_symlink() or not source_config.is_file():
        raise ValueError('config.yaml 不可讀或不是一般檔案；請整理設定後重試')
    config_bytes = source_config.read_bytes()
    isolate_sync_remote(config_bytes.decode('utf-8'), 'file:///local-placeholder')
    print(f'目標={repo} 狀態={state} uid={os.getuid()} port={args.port}')
    print('預覽：備份、啟動本機服務、保留內嵌樹、切換並讀回；失敗以 rollback.py 退回')
    if not args.apply:
        return 0
    no_bd()
    with workspace_gate(repo):
        ensure_tree_idle(beads / 'embeddeddolt')
    if stat.S_IMODE(beads.stat().st_mode) != 0o2770 or beads.stat().st_gid != target_config.group_id(CONFIG):
        raise RuntimeError('.beads 權限或群組不符基線')
    fragment = run(['systemctl', '--user', 'show', '--property=FragmentPath', '--value', SERVICE]).strip()
    if not fragment or Path(fragment).read_bytes() != target_config.render_unit(CONFIG).encode():
        raise RuntimeError('已安裝的服務範本與本工具不一致')
    active = subprocess.run(['systemctl', '--user', 'is-active', '--quiet', SERVICE], check=False)
    if active.returncode != 3:
        raise RuntimeError('服務不是明確的 inactive 狀態')
    if (beads / SAVED).exists() or (beads / 'dolt').exists():
        raise RuntimeError('目標已有保留樹或伺服器樹，停止')
    with socket.socket() as sock:
        sock.settimeout(0.2)
        if sock.connect_ex(('127.0.0.1', args.port)) == 0:
            raise RuntimeError('通訊埠已使用，停止')
    os.umask(0o007)
    validate_state(state, beads)
    with (state / '.operation.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        if (state / 'current').exists():
            raise RuntimeError('已有未封存的切換紀錄')
        usage = shutil.disk_usage(state)
        size = int(run(['du', '-sb', str(beads)]).split()[0])
        if usage.free < size * 3 + 1024 ** 3:
            raise RuntimeError('備份空間不足')
        work = state / 'current'
        work.mkdir()
        durable(work / '.migration-state', b'migration-state-v1\n')
        LOG_PATH = work / 'operations.log'
        log_event('切換開始')
        durable(work / 'metadata.original', original)
        durable(work / 'target.json', json.dumps({'repo': str(repo), 'port': args.port,
                                                   'uid': os.getuid(), 'project_id': config['project_id'], 'keep': args.keep,
                                                   'config_sha256': config_digest(), 'metadata_sha256': sha(original)}).encode())
        scratch_name = 'migration-scratch-' + uuid.uuid4().hex
        scratch_base = state / scratch_name
        scratch_base.mkdir()
        durable(scratch_base / '.migration-scratch', b'migration-scratch-v1\n')
        durable(scratch_base / 'target.json', (work / 'target.json').read_bytes())
        durable(work / 'scratch-id', (scratch_name + '\n').encode())
        recovery = ['uv', 'run', '--python', '3.14', '--no-project', 'python', '-I',
                    str(TOOLS / 'rollback.py'), '--config', str(args.config.resolve()),
                    '--immediate', '--apply', '--reviewed']
        print('失敗或中斷退回：' + shlex.join(recovery), flush=True)
        helper('permissions.py', ['--root', beads, '--out', work / 'permissions.json', '--owner', os.getuid()], repo)
        env = os.environ.copy()
        env.pop('BEADS_DOLT_SERVER_PORT', None)
        env['DOLT_ROOT_PATH'] = str(work / 'dolt-config')
        (work / 'dolt-config').mkdir()
        run(['dolt', 'config', '--global', '--add', 'metrics.disabled', 'true'], work, env)
        run(['dolt', 'config', '--global', '--add', 'user.name', 'beads-migration'], work, env)
        run(['dolt', 'config', '--global', '--add', 'user.email', 'beads-migration@invalid'], work, env)
        helper('snapshot.py', ['--bd', CONFIG['bd'], '--out', work / 'embedded.json'], repo, env)
        with workspace_gate(repo):
            log_event('已鎖定工作區')
            scratch = scratch_base / 'backup-repo'
            scratch.mkdir()
            run(['git', 'init', '-q', str(scratch)])
            run(['git', 'init', '-q', '--bare', str(work / 'remote.git')])
            if source_config.is_symlink() or not source_config.is_file() or source_config.read_bytes() != config_bytes:
                raise RuntimeError('config.yaml 已變動；請重新預覽')
            run(['cp', '-R', '--preserve=timestamps', str(beads), str(scratch / '.beads')])
            scratch_config = scratch / '.beads/config.yaml'
            if scratch_config.is_symlink() or not scratch_config.is_file() or scratch_config.read_bytes() != config_bytes:
                raise RuntimeError('複製的 config.yaml 與預覽不符')
            scratch_config.write_text(isolate_sync_remote(config_bytes.decode('utf-8'),
                                                         (work / 'remote.git').as_uri()), encoding='utf-8')
            helper('snapshot.py', ['--bd', CONFIG['bd'], '--out', work / 'copy.json',
                                   '--expected', work / 'embedded.json'], scratch, env)
            verify_scratch_location(scratch, env)
            run(['bd', '--sandbox', '--dolt-auto-commit', 'off', 'dolt', 'commit'], scratch, env)
            helper('db-fingerprint.py', ['--database', CONFIG['database'], '--local', scratch / '.beads/embeddeddolt' / CONFIG['database'],
                                         '--out', work / 'embedded-fingerprint.json'], scratch, env)
            backup_dir = state / 'backups'
            backup_dir.mkdir(exist_ok=True)
            backup = backup_dir / ('migration-backup-' + datetime.datetime.now(datetime.UTC).strftime('%Y%m%dT%H%M%SZ-') + uuid.uuid4().hex[:8])
            durable(work / 'backup-path', str(backup).encode())
            run(['bd', '--sandbox', 'backup', 'init', str(backup)], scratch, env)
            run(['bd', '--sandbox', 'backup', 'sync'], scratch, env)
            durable(backup / '.migration-backup', b'migration-backup-v1\n')
            helper('db-fingerprint.py', ['--database', CONFIG['database'], '--local', scratch / '.beads/embeddeddolt' / CONFIG['database'],
                                         '--out', work / 'embedded-after-backup.json',
                                         '--expected', work / 'embedded-fingerprint.json'], scratch, env)
            (beads / 'dolt').mkdir()
            run(['systemctl', '--user', 'start', SERVICE])
            ready(args.port)
            verify_server(beads, args.port)
            stage = scratch_base / 'server-repo'
            stage.mkdir()
            run(['git', 'init', '-q', str(stage)])
            env['BEADS_DOLT_SERVER_PORT'] = str(args.port)
            run(['bd', 'init', '--server', '--external', '--server-host', '127.0.0.1', '--server-port', str(args.port), '--prefix', CONFIG['prefix'], '--skip-agents', '--skip-hooks', '--non-interactive'], stage, env)
            normalize_init_remote(stage, (work / 'remote.git').as_uri())
            run(['bd', 'backup', 'restore', '--force', str(backup)], stage, env)
            helper('snapshot.py', ['--bd', CONFIG['bd'], '--out', work / 'stage.json', '--expected', work / 'embedded.json'], stage, env)
            helper('db-fingerprint.py', ['--database', CONFIG['database'], '--port', args.port, '--out', work / 'fingerprint-before.json'], stage, env)
            embedded_fp = json.loads((work / 'embedded-fingerprint.json').read_text())
            server_fp = json.loads((work / 'fingerprint-before.json').read_text())
            require_same_fingerprint(embedded_fp, server_fp)
            if sha(metadata.read_bytes()) != sha(original):
                raise RuntimeError('metadata 已變動')
            if gate_safety.contains_gate(beads / 'embeddeddolt'):
                raise RuntimeError('原內嵌樹含 gate 檔，不能移動')
            (beads / 'embeddeddolt').rename(beads / SAVED)
            config.update(dolt_mode='server', dolt_server_host='127.0.0.1', dolt_server_port=args.port)
            write_in_place(metadata, (json.dumps(config, indent=2) + '\n').encode(), sha(original))
            log_event('切換 metadata 完成')
        helper('snapshot.py', ['--bd', CONFIG['bd'], '--out', work / 'server.json', '--expected', work / 'embedded.json'], repo, env)
        helper('permissions.py', ['--root', beads, '--out', work / 'permissions-server.json', '--owner', os.getuid(), '--saved', SAVED, '--expected', work / 'permissions.json'], repo)
        helper('db-fingerprint.py', ['--database', CONFIG['database'], '--port', args.port, '--out', work / 'fingerprint-final.json'], stage, env)
        expired = retention.select(backup_dir, args.keep, {backup.name})
        for path in expired:
            print(f'刪除過期備份 {path}')
        retention.delete(backup_dir, expired)
        durable(work / 'switch-complete', b'ok\n')
        state_retention.cleanup_safe(state, args.keep, repo, os.getuid(), log_event)
        log_event('切換驗證完成')
        print('切換讀回與權限檢查通過')
    return 0


if __name__ == '__main__':
    try:
        sys.exit(main())
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as error:
        print(f'切換停止：{error}', file=sys.stderr)
        sys.exit(1)
