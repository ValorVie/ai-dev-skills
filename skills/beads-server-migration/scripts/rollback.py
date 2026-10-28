#!/usr/bin/env python3
"""Recover a Beads switch; default is a preview without mutation."""
import argparse
import datetime
import fcntl
import json
import os
import re
import shutil
import stat
import subprocess
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from metadata_io import sha, write_in_place
from switch import SAVED, SERVICE, durable, helper, no_bd, run, scratch_root, validate_state, verify_server, workspace_gate
import switch as switch_module
import permissions
import retention
import staged_acl
import state_retention
import gate_safety
import target_config


def is_interrupted_write(current, before, after):
    # ponytail: small metadata permits O(n²) comparisons; use a linear scan if it grows.
    return current == after or any(current == after[:n] + before[n:] for n in range(len(after) + 1))


def ensure_durable(path, data):
    if path.is_symlink():
        raise ValueError('檢查點不能是符號連結')
    if path.exists():
        if not path.is_file() or path.read_bytes() != data:
            raise ValueError('既有檢查點不符')
    else:
        temporary = path.parent / ('.' + path.name + '.' + uuid.uuid4().hex)
        durable(temporary, data)
        os.link(temporary, path, follow_symlinks=False)
        directory = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(directory)
            temporary.unlink()
            os.fsync(directory)
        finally:
            os.close(directory)


def tree_identity(path):
    if path.is_symlink() or not path.is_dir():
        raise ValueError('資料樹不可用')
    info = path.stat()
    return [info.st_dev, info.st_ino]


def locate_tree(first, second, identity):
    if first.is_symlink() or second.is_symlink() or first.exists() == second.exists():
        raise RuntimeError('資料樹位置不明或重複')
    path = first if first.exists() else second
    if tree_identity(path) != identity:
        raise RuntimeError('資料樹身分與檢查點不符')
    return path


def read_metadata(path):
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    with os.fdopen(fd, 'rb') as stream:
        info = os.fstat(stream.fileno())
        if not stat.S_ISREG(info.st_mode):
            raise ValueError('metadata 不是一般檔案')
        return stream.read(), [info.st_dev, info.st_ino]


def service_active():
    state = run(['systemctl', '--user', 'show', '--property=ActiveState', '--value', SERVICE]).strip()
    if state == 'active':
        return True
    if state in ('inactive', 'failed'):
        pid = run(['systemctl', '--user', 'show', '--property=MainPID', '--value', SERVICE]).strip()
        if pid == '0':
            return False
    raise RuntimeError('服務尚未完全停止或狀態不明')


def ensure_tree_idle(path, allowed_pids=()):
    switch_module.ensure_tree_idle(path, allowed_pids)


def preflight_trees(repo, beads, work, port):
    """Check recovery feasibility before writing markers or stopping a service."""
    if not state_retention.inspectable():
        raise RuntimeError('無法確認退回所需程序可見性')
    with workspace_gate(repo):
        active = service_active()
        server = beads / 'dolt'
        if active and (server.is_symlink() or not server.is_dir()):
            raise RuntimeError('服務運行時伺服器資料樹不符')
        allowed = {verify_server(beads, port)} if active else set()
        for path in (beads / SAVED, beads / 'embeddeddolt', server, work / 'server-data'):
            if path.is_symlink():
                raise RuntimeError('資料樹不可為符號連結')
            if path.exists():
                if not path.is_dir():
                    raise RuntimeError('資料樹不可用')
                ensure_tree_idle(path, allowed if active and path == server else ())


def verify_disabled():
    active = subprocess.run(['systemctl', '--user', 'is-active', SERVICE], capture_output=True, text=True, timeout=30)
    enabled = subprocess.run(['systemctl', '--user', 'is-enabled', SERVICE], capture_output=True, text=True, timeout=30)
    if (active.returncode != 3 or active.stdout.strip() not in ('inactive', 'failed')
            or enabled.returncode != 1 or enabled.stdout.strip() != 'disabled' or service_active()):
        raise RuntimeError('服務停用狀態讀回不符')
    switch_module.log_event('服務讀回：' + active.stdout.strip() + '／disabled')


def disable_service():
    run(['systemctl', '--user', 'disable', SERVICE])
    verify_disabled()


def completed_saved(beads, archive):
    source = beads / SAVED
    destination = archive / 'reswitch-saved-tree'
    if source.exists() or source.is_symlink():
        if destination.exists() or destination.is_symlink():
            raise ValueError('原樹位置重複')
        return source
    intent = archive / 'reswitch-intent.json'
    completed = archive / 'reswitch-complete'
    if any(p.is_symlink() or not p.is_file() for p in (intent, completed)):
        raise ValueError('封存原樹的完成紀錄不可用')
    data = intent.read_bytes()
    plan = json.loads(data)
    if completed.read_bytes() != (sha(data) + '\n').encode() or tree_identity(destination) != plan['tree']:
        raise ValueError('封存原樹與完成紀錄不符')
    return destination


def verify_completed(beads, archive, target, mode, saved_override=None):
    metadata = beads / 'metadata.json'
    backup = archive / 'metadata.original'
    if any(path.is_symlink() or not path.is_file() for path in (metadata, backup)):
        raise ValueError('退回後 metadata 或原始備份不可用')
    original = backup.read_bytes()
    if sha(original) != target.get('metadata_sha256'):
        raise ValueError('原 metadata 備份雜湊不符')
    before = json.loads(original)
    actual = json.loads(metadata.read_bytes())
    if (not isinstance(before, dict) or not isinstance(actual, dict)
            or before.get('dolt_mode') != 'embedded' or actual.get('dolt_mode') != 'embedded'
            or not target.get('project_id') or before.get('project_id') != target['project_id']
            or actual.get('project_id') != target['project_id']
            or before.get('dolt_database') != switch_module.CONFIG['database'] or actual.get('dolt_database') != switch_module.CONFIG['database']):
        raise ValueError('退回後 metadata 模式或專案身分漂移')
    trees = [beads / 'embeddeddolt']
    saved = (saved_override or completed_saved(beads, archive)) if mode == 'after-write' else beads / SAVED
    if mode == 'after-write':
        trees.append(saved)
    elif saved.exists() or saved.is_symlink():
        raise ValueError('立即退回後仍有保留原樹')
    dolt = beads / 'dolt'
    if dolt.exists() or dolt.is_symlink():
        raise ValueError('退回後仍有伺服器資料樹')
    for tree in trees:
        for path in (tree, tree / switch_module.CONFIG['database'], tree / switch_module.CONFIG['database'] / '.dolt', tree / switch_module.CONFIG['database'] / '.dolt/noms'):
            if path.is_symlink() or not path.is_dir():
                raise ValueError('退回後內嵌資料樹不可用')
        for path in (tree / switch_module.CONFIG['database'] / '.dolt/noms/manifest', tree / switch_module.CONFIG['database'] / '.dolt/repo_state.json'):
            if path.is_symlink() or not path.is_file():
                raise ValueError('退回後內嵌資料檔不可用')


def prepare_after_write(repo, beads, state, work, target):
    if not (work / 'switch-complete').is_file() or not (beads / SAVED).is_dir():
        raise RuntimeError('事後退回需要已完成切換及原內嵌樹')
    if (beads / 'embeddeddolt').exists() or (beads / 'embeddeddolt').is_symlink():
        raise RuntimeError('已有待處理的內嵌樹')
    verify_server(beads, target['port'])
    needed = int(run(['du', '-sb', str(beads / 'dolt')]).split()[0]) * 3 + 1024 ** 3
    if shutil.disk_usage(work).free < needed:
        raise RuntimeError('事後退回的備份空間不足')
    attempt_name = 'after-write-' + uuid.uuid4().hex
    attempt = work / attempt_name
    attempt.mkdir()
    env = os.environ.copy()
    env['BEADS_DOLT_SERVER_PORT'] = str(target['port'])
    env['DOLT_ROOT_PATH'] = str(work / 'dolt-config')
    stage = scratch_root(state, work) / 'server-repo'
    if stage.is_symlink() or not stage.is_dir():
        raise RuntimeError('scratch 伺服器 repo 不可用')
    helper('snapshot.py', ['--bd', 'bd', '--out', attempt / 'server-before.json'], repo, env)
    helper('db-fingerprint.py', ['--database', switch_module.CONFIG['database'], '--port', target['port'],
                                 '--out', attempt / 'fingerprint-before.json'], stage, env)
    backup_root = state / 'backups'
    name = 'migration-backup-' + datetime.datetime.now(datetime.UTC).strftime('%Y%m%dT%H%M%SZ-') + uuid.uuid4().hex[:8]
    backup = backup_root / name
    local_env = env.copy()
    local_env.pop('BEADS_DOLT_SERVER_PORT', None)
    with workspace_gate(repo):
        helper('db-fingerprint.py', ['--database', switch_module.CONFIG['database'], '--port', target['port'],
                                     '--out', attempt / 'fingerprint-locked.json',
                                     '--expected', attempt / 'fingerprint-before.json'], stage, env)
        run(['bd', '--sandbox', '--dolt-auto-commit', 'off', 'dolt', 'commit'], stage, env)
        helper('db-fingerprint.py', ['--database', switch_module.CONFIG['database'], '--port', target['port'],
                                     '--out', attempt / 'fingerprint-committed.json'], stage, env)
        durable(attempt / 'backup-path', str(backup).encode())
        run(['bd', '--sandbox', '--dolt-auto-commit', 'off', 'backup', 'init', str(backup)], stage, env)
        run(['bd', '--sandbox', '--dolt-auto-commit', 'off', 'backup', 'sync'], stage, env)
        durable(backup / '.migration-backup', b'migration-backup-v1\n')
        helper('snapshot.py', ['--bd', 'bd', '--out', attempt / 'server-after.json',
                               '--expected', attempt / 'server-before.json'], stage, env)
        helper('db-fingerprint.py', ['--database', switch_module.CONFIG['database'], '--port', target['port'],
                                     '--out', attempt / 'fingerprint.json',
                                     '--expected', attempt / 'fingerprint-committed.json'], stage, env)
        dolt_root = attempt / 'restore-config'
        dolt_root.mkdir()
        local_env['DOLT_ROOT_PATH'] = str(dolt_root)
        run(['dolt', 'config', '--global', '--add', 'metrics.disabled', 'true'], work, local_env)
        run(['dolt', 'config', '--global', '--add', 'user.name', 'beads-migration'], work, local_env)
        run(['dolt', 'config', '--global', '--add', 'user.email', 'beads-migration@invalid'], work, local_env)
        baseline = json.loads((work / 'permissions.json').read_text())
        staging_parent = attempt / 'restore-staging'
        staging_parent.mkdir()
        staged_acl.apply(staging_parent, baseline['.'], beads)
        staging = staging_parent / 'embeddeddolt'
        staging.mkdir()
        run(['dolt', 'backup', 'restore', backup.as_uri(), switch_module.CONFIG['database']], staging, local_env)
        helper('db-fingerprint.py', ['--database', switch_module.CONFIG['database'], '--local', staging / switch_module.CONFIG['database'],
                                     '--out', attempt / 'local-fingerprint.json'], repo, local_env)
        server = json.loads((attempt / 'fingerprint.json').read_text())
        local = json.loads((attempt / 'local-fingerprint.json').read_text())
        switch_module.require_same_fingerprint(server, local)
        original_tree = {('.' if path == 'embeddeddolt' else path[len('embeddeddolt/'):]): value
                         for path, value in baseline.items()
                         if path == 'embeddeddolt' or path.startswith('embeddeddolt/')}
        staged_acl.reconcile(staging, original_tree, beads)
        combined = permissions.capture(beads)
        for path, value in permissions.capture(staging).items():
            combined['embeddeddolt' if path == '.' else 'embeddeddolt/' + path] = value
        errors, added = permissions.compare_later(baseline, combined, os.getuid(), target_config.group_id(switch_module.CONFIG), SAVED)
        durable(attempt / 'staged-permissions.json', json.dumps(combined, sort_keys=True, indent=2).encode())
        durable(attempt / 'staged-inventory.json', json.dumps(added, sort_keys=True, indent=2).encode())
        if errors:
            for error in errors:
                print(error, file=sys.stderr)
            raise RuntimeError('暫存還原樹的權限不符')
        original = (work / 'metadata.original').read_bytes()
        expected = dict(json.loads(original))
        expected.update(dolt_mode='server', dolt_server_host='127.0.0.1', dolt_server_port=target['port'])
        source = (json.dumps(expected, indent=2) + '\n').encode()
        current, metadata_id = read_metadata(beads / 'metadata.json')
        if current != source:
            raise RuntimeError('metadata 已變動')
        if gate_safety.contains_gate(staging):
            raise RuntimeError('重建樹含 gate 檔，不能移動')
        plan = {'attempt': attempt_name, 'backup': name, 'saved': tree_identity(beads / SAVED),
                'server': tree_identity(beads / 'dolt'), 'staging': tree_identity(staging),
                'metadata': metadata_id, 'source_sha': sha(source), 'original_sha': sha(original),
                'fingerprint_sha': sha((attempt / 'fingerprint.json').read_bytes()),
                'local_sha': sha((attempt / 'local-fingerprint.json').read_bytes()),
                'snapshot_sha': sha((attempt / 'server-after.json').read_bytes()),
                'baseline_sha': sha((work / 'permissions.json').read_bytes())}
        ensure_durable(work / 'after-write-plan.json', (json.dumps(plan, sort_keys=True) + '\n').encode())
    return plan


def after_write(repo, beads, state, work, target, attempt_id):
    plan_path = work / 'after-write-plan.json'
    if plan_path.is_symlink():
        raise RuntimeError('事後退回檢查點不可為符號連結')
    if plan_path.is_file():
        plan = json.loads(plan_path.read_text())
    else:
        plan = prepare_after_write(repo, beads, state, work, target)
    required = {'attempt', 'backup', 'saved', 'server', 'staging', 'metadata', 'source_sha', 'original_sha',
                'fingerprint_sha', 'local_sha', 'snapshot_sha', 'baseline_sha'}
    if not isinstance(plan, dict) or set(plan) != required:
        raise RuntimeError('事後退回檢查點格式不符')
    if not isinstance(plan['attempt'], str) or not re.fullmatch(r'after-write-[0-9a-f]{32}', plan['attempt']):
        raise RuntimeError('事後退回嘗試名稱不符')
    attempt = work / plan['attempt']
    staging_parent = attempt / 'restore-staging'
    if any(p.is_symlink() or not p.is_dir() for p in (attempt, staging_parent)):
        raise RuntimeError('事後退回暫存路徑不符')
    backup_root = state / 'backups'
    if not isinstance(plan['backup'], str):
        raise RuntimeError('事後退回備份名稱不符')
    backup = backup_root / plan['backup']
    if backup.parent != backup_root or not retention.owned(backup):
        raise RuntimeError('事後退回備份不符')
    artifacts = ((attempt / 'fingerprint.json', 'fingerprint_sha'),
                 (attempt / 'local-fingerprint.json', 'local_sha'),
                 (attempt / 'server-after.json', 'snapshot_sha'),
                 (work / 'permissions.json', 'baseline_sha'), (work / 'metadata.original', 'original_sha'))
    for path, key in artifacts:
        if path.is_symlink() or not path.is_file() or sha(path.read_bytes()) != plan[key]:
            raise RuntimeError('事後退回證據與檢查點不符')
    original = (work / 'metadata.original').read_bytes()
    expected = dict(json.loads(original))
    expected.update(dolt_mode='server', dolt_server_host='127.0.0.1', dolt_server_port=target['port'])
    source = (json.dumps(expected, indent=2) + '\n').encode()
    if sha(source) != plan['source_sha']:
        raise RuntimeError('事後退回 metadata 來源不符')
    env = os.environ.copy()
    env['BEADS_DOLT_SERVER_PORT'] = str(target['port'])
    env['DOLT_ROOT_PATH'] = str(work / 'dolt-config')
    stage = scratch_root(state, work) / 'server-repo'
    if stage.is_symlink() or not stage.is_dir():
        raise RuntimeError('scratch 伺服器 repo 不可用')
    local_env = env.copy()
    local_env.pop('BEADS_DOLT_SERVER_PORT', None)
    local_env['DOLT_ROOT_PATH'] = str(attempt / 'restore-config')
    plan_hash = sha(plan_path.read_bytes()).encode() + b'\n'
    previous_present = True
    for name in ('tree', 'metadata', 'stop', 'disable', 'server', 'finish'):
        marker = work / ('after-write-' + name + '.intent')
        if marker.is_symlink() or (marker.exists() and (not marker.is_file() or marker.read_bytes() != plan_hash)):
            raise RuntimeError('事後退回階段檢查點不符')
        present = marker.is_file()
        if present and not previous_present:
            raise RuntimeError('事後退回階段順序不符')
        previous_present = present
    with workspace_gate(repo):
        if tree_identity(beads / SAVED) != plan['saved']:
            raise RuntimeError('保留原樹身分不符')
        staging = staging_parent / 'embeddeddolt'
        embedded = beads / 'embeddeddolt'
        rebuilt = locate_tree(staging, embedded, plan['staging'])
        server_data = beads / 'dolt'
        destination = work / 'server-data'
        server_tree = locate_tree(server_data, destination, plan['server'])
        metadata, metadata_id = read_metadata(beads / 'metadata.json')
        if metadata_id != plan['metadata']:
            raise RuntimeError('事後退回 metadata 身分不符')
        metadata_step = work / 'after-write-metadata.intent'
        if metadata_step.is_file():
            if not is_interrupted_write(metadata, source, original):
                raise RuntimeError('事後退回 metadata 與檢查點不符')
        elif metadata != source:
            raise RuntimeError('事後退回 metadata 未符合原狀態')
        active = service_active()
        if active:
            if server_tree != server_data:
                raise RuntimeError('服務運行時資料樹位置不符')
            verify_server(beads, target['port'])
            helper('db-fingerprint.py', ['--database', switch_module.CONFIG['database'], '--port', target['port'], '--out',
                                        attempt / ('server-check-' + uuid.uuid4().hex + '.json'),
                                        '--expected', attempt / 'fingerprint.json'], stage, env)
        else:
            ensure_tree_idle(server_tree)
            helper('db-fingerprint.py', ['--database', switch_module.CONFIG['database'], '--local', server_tree / switch_module.CONFIG['database'], '--out',
                                        attempt / ('offline-check-' + uuid.uuid4().hex + '.json'),
                                        '--expected', attempt / 'fingerprint.json'], repo, local_env)
        if tree_identity(server_tree) != plan['server'] or sha((attempt / 'fingerprint.json').read_bytes()) != plan['fingerprint_sha']:
            raise RuntimeError('伺服器資料樹或指紋在核對期間變動')
        ensure_tree_idle(rebuilt)
        helper('db-fingerprint.py', ['--database', switch_module.CONFIG['database'], '--local', rebuilt / switch_module.CONFIG['database'], '--out',
                                    attempt / ('rebuilt-check-' + uuid.uuid4().hex + '.json'),
                                    '--expected', attempt / 'local-fingerprint.json'], repo, local_env)
        if tree_identity(rebuilt) != plan['staging']:
            raise RuntimeError('重建樹在核對期間變動')
        tree_step = work / 'after-write-tree.intent'
        if rebuilt == embedded and not tree_step.is_file():
            raise RuntimeError('缺少搬入重建樹的檢查點')
        ensure_durable(tree_step, plan_hash)
        if rebuilt == staging:
            if gate_safety.contains_gate(staging):
                raise RuntimeError('重建樹含 gate 檔，不能移動')
            staging.rename(embedded)
        helper('permissions.py', ['--root', beads, '--out', attempt / ('permissions-' + uuid.uuid4().hex + '.json'),
                                  '--owner', os.getuid(), '--group', target_config.group_id(switch_module.CONFIG), '--phase', 'later', '--saved', SAVED,
                                  '--expected', work / 'permissions.json'], repo)
        ensure_durable(metadata_step, plan_hash)
        metadata, metadata_id = read_metadata(beads / 'metadata.json')
        if metadata_id != plan['metadata'] or not is_interrupted_write(metadata, source, original):
            raise RuntimeError('事後退回 metadata 與檢查點不符')
        if metadata != original:
            write_in_place(beads / 'metadata.json', original, sha(metadata), plan['metadata'])
        stop_step = work / 'after-write-stop.intent'
        ensure_durable(stop_step, plan_hash)
        if active:
            verify_server(beads, target['port'])
            run(['systemctl', '--user', 'stop', SERVICE])
            if service_active():
                raise RuntimeError('服務停止後仍在運行')
        ensure_tree_idle(server_tree)
        helper('db-fingerprint.py', ['--database', switch_module.CONFIG['database'], '--local', server_tree / switch_module.CONFIG['database'], '--out',
                                    attempt / ('stopped-check-' + uuid.uuid4().hex + '.json'),
                                    '--expected', attempt / 'fingerprint.json'], repo, local_env)
        if tree_identity(server_tree) != plan['server'] or sha((attempt / 'fingerprint.json').read_bytes()) != plan['fingerprint_sha']:
            raise RuntimeError('停止後的資料樹或指紋變動')
        ensure_durable(work / 'after-write-disable.intent', plan_hash)
        disable_service()
        server_step = work / 'after-write-server.intent'
        if server_tree == destination and not server_step.is_file():
            raise RuntimeError('缺少搬移伺服器樹的檢查點')
        ensure_durable(server_step, plan_hash)
        if server_tree == server_data:
            if gate_safety.contains_gate(server_data):
                raise RuntimeError('伺服器資料樹含 gate 檔，不能移動')
            server_data.rename(destination)
    helper('snapshot.py', ['--bd', 'bd', '--out', attempt / ('embedded-' + uuid.uuid4().hex + '.json'),
                           '--expected', attempt / 'server-after.json'], repo, local_env)
    helper('permissions.py', ['--root', beads, '--out', attempt / ('permissions-final-' + uuid.uuid4().hex + '.json'),
                              '--owner', os.getuid(), '--group', target_config.group_id(switch_module.CONFIG), '--phase', 'later', '--saved', SAVED,
                              '--expected', work / 'permissions.json'], repo)
    ensure_durable(work / 'after-write-finish.intent', plan_hash)
    expired = retention.select(backup_root, target['keep'], {backup.name})
    for path in expired:
        print(f'刪除過期備份 {path}')
    retention.delete(backup_root, expired)
    ensure_durable(attempt / '.migration-attempt-complete', b'ok\n')
    ensure_durable(work / 'rollback-complete', b'after-write\n')
    durable(work / ('rollback-attempt-' + attempt_id + '.completed'), b'ok\n')
    switch_module.log_event('事後退回驗證完成')
    archived = state / ('completed-' + uuid.uuid4().hex)
    if gate_safety.contains_gate(work):
        raise RuntimeError('完成紀錄含 gate 檔，不能移動')
    work.rename(archived)
    switch_module.LOG_PATH = archived / 'operations.log'
    state_retention.cleanup_safe(state, target['keep'], repo, os.getuid(), switch_module.log_event)
    print(f'事後退回完成，原樹及備份保留於 {archived} 和 {beads / SAVED}')

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--config', type=Path, required=True)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--immediate', action='store_true')
    mode.add_argument('--after-write', action='store_true')
    parser.add_argument('--apply', action='store_true')
    parser.add_argument('--reviewed', action='store_true')
    global SERVICE
    args = parser.parse_args()
    switch_module.configure(args.config)
    SERVICE = switch_module.SERVICE
    args.repo, args.state = Path(switch_module.CONFIG['repo']), Path(switch_module.CONFIG['state'])
    if args.apply != args.reviewed:
        raise ValueError('需要同時指定 --apply --reviewed')
    switch_module.reject_selector_environment()
    repo = args.repo.resolve(strict=True)
    if args.apply and not switch_module.execution_allowed(repo):
        raise RuntimeError('套用目標不是指定離線容器或設定宣告的主機與帳號')
    beads = repo / '.beads'
    switch_module.reject_workspace_overrides(beads)
    state = args.state.absolute()
    work = state / 'current'
    if state != state.resolve(strict=False) or '.cache' in state.parts or state == beads or beads in state.parents:
        raise ValueError('狀態目錄必須位於 Beads 之外且不可含符號連結')
    if not work.exists() and beads.is_dir() and not beads.is_symlink():
        archives = sorted((p for p in state.glob('completed-*') if (p / 'rollback-complete').is_file()),
                          key=lambda p: ((p / 'switch-complete') if (p / 'switch-complete').is_file()
                                         else (p / 'rollback-complete')).stat().st_mtime_ns, reverse=True)
        if archives:
            recent = archives[0]
            previous = json.loads((recent / 'target.json').read_text())
            switch_module.check_target_config(previous)
            mode_name = (recent / 'rollback-complete').read_text().strip()
            if previous['repo'] != str(repo) or previous['uid'] != os.getuid() or mode_name != ('immediate' if args.immediate else 'after-write'):
                raise ValueError('已完成的退回紀錄不符')
            verify_completed(beads, recent, previous, mode_name)
            baseline = json.loads((recent / 'permissions.json').read_text())
            current = permissions.capture(beads)
            if args.immediate:
                errors = permissions.compare_immediate(baseline, current, os.getuid())
            else:
                saved_tree = completed_saved(beads, recent)
                if saved_tree != beads / SAVED:
                    for path, value in permissions.capture(saved_tree).items():
                        current[SAVED if path == '.' else SAVED + '/' + path] = value
                errors, _ = permissions.compare_later(baseline, current, os.getuid(), target_config.group_id(switch_module.CONFIG), SAVED)
            if errors:
                raise RuntimeError('退回後權限狀態漂移')
            if args.apply:
                verify_disabled()
            print('已退回且權限一致；不異動')
            return 0
    if beads.is_symlink() or work.is_symlink() or not work.is_dir():
        raise ValueError('無效的目標或切換紀錄')
    target = json.loads((work / 'target.json').read_text())
    switch_module.check_target_config(target)
    if target['repo'] != str(repo) or target['uid'] != os.getuid() or beads.stat().st_uid != os.getuid():
        raise ValueError('目標或執行帳號不符')
    if work.stat().st_dev != beads.stat().st_dev:
        raise ValueError('狀態目錄必須在同一檔案系統')
    if sha((work / 'metadata.original').read_bytes()) != target['metadata_sha256']:
        raise ValueError('原 metadata 備份雜湊不符')
    print(f'目標={repo} 模式={"立即" if args.immediate else "事後"}；保留備份與原內嵌資料')
    if not args.apply:
        return 0
    validate_state(state, beads)
    if work.stat().st_gid != target_config.group_id(switch_module.CONFIG) or not work.stat().st_mode & stat.S_ISGID:
        raise ValueError('切換紀錄群組或 setgid 不符')
    preflight_trees(repo, beads, work, target['port'])
    switch_module.LOG_PATH = work / 'operations.log'
    switch_module.log_event('退回開始：' + ('immediate' if args.immediate else 'after-write'))
    os.umask(0o007)
    with (state / '.operation.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        if shutil.disk_usage(work).free < 1024 ** 3:
            raise RuntimeError('退回紀錄空間不足')
        attempt_id = uuid.uuid4().hex
        durable(work / ('rollback-attempt-' + attempt_id + '.started'), b'started\n')
        no_bd()
        if args.after_write:
            after_write(repo, beads, state, work, target, attempt_id)
            return 0
        metadata = beads / 'metadata.json'
        if metadata.is_symlink() or not metadata.is_file():
            raise RuntimeError('metadata 不可用')
        original = (work / 'metadata.original').read_bytes()
        old = json.loads(original)
        server = dict(old)
        server.update(dolt_mode='server', dolt_server_host='127.0.0.1', dolt_server_port=target['port'])
        server_bytes = (json.dumps(server, indent=2) + '\n').encode()
        fingerprint = work / ('fingerprint-final.json' if (work / 'switch-complete').exists() else 'fingerprint-before.json')
        with workspace_gate(repo):
            saved = beads / SAVED
            embedded = beads / 'embeddeddolt'
            server_data = beads / 'dolt'
            destination = work / 'server-data'
            intent_path = work / 'immediate-intent.json'
            source_path = work / 'metadata-rollback-source'
            if any(p.is_symlink() for p in (intent_path, source_path, fingerprint, saved, embedded, server_data, destination)):
                raise RuntimeError('退回檢查點不可為符號連結')
            has_intent = intent_path.is_file()
            intent = json.loads(intent_path.read_text()) if has_intent else None
            if has_intent and (not isinstance(intent, dict)
                               or set(intent) != {'tree', 'server', 'metadata', 'source_sha', 'fingerprint'}):
                raise RuntimeError('退回檢查點格式不符')
            if saved.exists() and embedded.exists():
                raise RuntimeError('已有另一份內嵌樹')
            tree = saved if saved.exists() else embedded
            tree_id = tree_identity(tree)
            if server_data.exists() and destination.exists():
                raise RuntimeError('已有兩份伺服器資料樹')
            server_tree = server_data if server_data.exists() else destination if destination.exists() else None
            server_id = tree_identity(server_tree) if server_tree else None
            current, metadata_id = read_metadata(metadata)
            if has_intent:
                if (not source_path.is_file() or intent.get('tree') != tree_id
                        or intent.get('server') != server_id or intent.get('metadata') != metadata_id
                        or ((saved.exists() or (work / 'switch-complete').exists())
                            and intent.get('fingerprint') is None)
                        or (intent.get('fingerprint') is not None
                            and (not fingerprint.is_file() or intent['fingerprint'] != sha(fingerprint.read_bytes())))):
                    raise RuntimeError('退回檢查點與資料樹不符')
                source = source_path.read_bytes()
                if sha(source) != intent.get('source_sha') or not is_interrupted_write(current, source, original):
                    raise RuntimeError('metadata 與退回檢查點不符')
            else:
                if destination.exists() or (not saved.exists() and (work / 'switch-complete').exists()):
                    raise RuntimeError('缺少可驗證的退回檢查點')
                switch_partial = (not (work / 'switch-complete').exists() and saved.is_dir()
                                  and is_interrupted_write(current, original, server_bytes))
                if current not in (original, server_bytes) and not switch_partial:
                    raise RuntimeError('metadata 已被其他操作改動')
                if not saved.exists() and current != original:
                    raise RuntimeError('原內嵌樹與 metadata 不一致')
                source = current
            if saved.exists() and not fingerprint.is_file():
                raise RuntimeError('缺少切換前的伺服器指紋，不能立即退回')
            active = service_active()
            if active:
                if not server_data.is_dir() or server_data.is_symlink():
                    raise RuntimeError('服務運行時伺服器資料樹不符')
                verify_server(beads, target['port'])
                if saved.exists() or (has_intent and intent.get('fingerprint')):
                    helper('db-fingerprint.py', ['--database', switch_module.CONFIG['database'], '--port', target['port'], '--out',
                                                work / ('rollback-fingerprint-' + uuid.uuid4().hex + '.json'),
                                                '--expected', fingerprint], repo)
            elif saved.exists() and not has_intent:
                if server_tree is None:
                    raise RuntimeError('缺少伺服器資料樹')
                ensure_tree_idle(server_tree)
                fingerprint_sha = sha(fingerprint.read_bytes())
                helper('db-fingerprint.py', ['--database', switch_module.CONFIG['database'], '--local', server_tree / switch_module.CONFIG['database'], '--out',
                                            work / ('rollback-initial-fingerprint-' + uuid.uuid4().hex + '.json'),
                                            '--expected', fingerprint], repo)
                if tree_identity(server_tree) != server_id or sha(fingerprint.read_bytes()) != fingerprint_sha:
                    raise RuntimeError('資料樹或指紋在核對期間變動')
            if not has_intent:
                observed, observed_id = read_metadata(metadata)
                if observed != source or observed_id != metadata_id or tree_identity(tree) != tree_id:
                    raise RuntimeError('metadata 或原樹在核對期間變動')
                ensure_durable(source_path, source)
                intent = {'tree': tree_id, 'server': server_id, 'metadata': metadata_id,
                          'source_sha': sha(source),
                          'fingerprint': sha(fingerprint.read_bytes()) if saved.exists() else None}
                ensure_durable(intent_path, (json.dumps(intent, sort_keys=True) + '\n').encode())
            if active:
                run(['systemctl', '--user', 'stop', SERVICE])
                if service_active():
                    raise RuntimeError('服務停止後仍在運行')
            if intent['fingerprint']:
                if server_tree is None or not fingerprint.is_file():
                    raise RuntimeError('缺少伺服器資料樹或指紋')
                ensure_tree_idle(server_tree)
                helper('db-fingerprint.py', ['--database', switch_module.CONFIG['database'], '--local', server_tree / switch_module.CONFIG['database'], '--out',
                                            work / ('rollback-local-fingerprint-' + uuid.uuid4().hex + '.json'),
                                            '--expected', fingerprint], repo)
                if tree_identity(server_tree) != intent['server'] or sha(fingerprint.read_bytes()) != intent['fingerprint']:
                    raise RuntimeError('資料樹或指紋在核對期間變動')
            if server_data.exists():
                if gate_safety.contains_gate(server_data):
                    raise RuntimeError('伺服器資料樹含 gate 檔，不能移動')
                server_data.rename(destination)
            if saved.exists():
                if gate_safety.contains_gate(saved):
                    raise RuntimeError('原內嵌樹含 gate 檔，不能移動')
                saved.rename(embedded)
            if tree_identity(embedded) != intent['tree']:
                raise RuntimeError('原內嵌樹身分不符')
            current, metadata_id = read_metadata(metadata)
            if metadata_id != intent['metadata'] or not is_interrupted_write(current, source, original):
                raise RuntimeError('metadata 與退回檢查點不符')
            if current != original:
                write_in_place(metadata, original, sha(current), intent['metadata'])
            disable_service()
        helper('permissions.py', ['--root', beads, '--out', work / ('permissions-rollback-' + uuid.uuid4().hex + '.json'),
                                  '--owner', os.getuid(), '--phase', 'immediate', '--expected', work / 'permissions.json'], repo)
        env = os.environ.copy()
        env.pop('BEADS_DOLT_SERVER_PORT', None)
        if (work / 'embedded.json').is_file():
            helper('snapshot.py', ['--bd', 'bd', '--out', work / ('rollback-' + uuid.uuid4().hex + '.json'),
                                   '--expected', work / 'embedded.json'], repo, env)
        helper('permissions.py', ['--root', beads, '--out', work / ('permissions-final-' + uuid.uuid4().hex + '.json'),
                                  '--owner', os.getuid(), '--phase', 'immediate', '--expected', work / 'permissions.json'], repo)
        ensure_durable(work / 'rollback-complete', b'immediate\n')
        durable(work / ('rollback-attempt-' + attempt_id + '.completed'), b'ok\n')
        switch_module.log_event('立即退回驗證完成')
        archived = state / ('completed-' + uuid.uuid4().hex)
        if gate_safety.contains_gate(work):
            raise RuntimeError('完成紀錄含 gate 檔，不能移動')
        work.rename(archived)
        switch_module.LOG_PATH = archived / 'operations.log'
        state_retention.cleanup_safe(state, target['keep'], repo, os.getuid(), switch_module.log_event)
        print(f'立即退回完成，紀錄與伺服器資料保留於 {archived}')
    return 0


if __name__ == '__main__':
    try:
        sys.exit(main())
    except (OSError, ValueError, KeyError, RuntimeError, subprocess.SubprocessError) as error:
        print(f'退回停止：{error}', file=sys.stderr)
        sys.exit(1)
