#!/usr/bin/env python3
"""Retain completed migration records without deleting active or failed work."""
import json
import hashlib
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import gate_safety

ARCHIVE = re.compile(r'completed-[0-9a-f]{32}\Z')
STARTED = re.compile(r'rollback-attempt-([0-9a-f]{32})\.started\Z')
AFTER_WRITE = re.compile(r'after-write-[0-9a-f]{32}\Z')


def marked(path, repo, uid):
    if path.is_symlink() or not path.is_dir() or not ARCHIVE.fullmatch(path.name):
        return False
    for name in ('.migration-state', 'target.json', 'switch-complete', 'rollback-complete', 'operations.log'):
        item = path / name
        if item.is_symlink() or not item.is_file():
            return False
    try:
        target = json.loads((path / 'target.json').read_text())
        if ((path / '.migration-state').read_text() != 'migration-state-v1\n'
                or (path / 'switch-complete').read_text() != 'ok\n'
                or (path / 'rollback-complete').read_text() not in ('immediate\n', 'after-write\n')
                or target.get('repo') != str(repo) or target.get('uid') != uid):
            return False
        intent, completed = path / 'reswitch-intent.json', path / 'reswitch-complete'
        before, tree = path / 'reswitch-before.json', path / 'reswitch-saved-tree'
        if any(p.exists() or p.is_symlink() for p in (intent, completed, before, tree)):
            if (any(p.is_symlink() for p in (intent, completed, before, tree))
                    or not intent.is_file() or not completed.is_file() or not before.is_file() or not tree.is_dir()
                    or completed.read_text() != hashlib.sha256(intent.read_bytes()).hexdigest() + '\n'):
                return False
            plan = json.loads(intent.read_text())
            info = tree.stat()
            if (not isinstance(plan, dict) or plan.get('tree') != [info.st_dev, info.st_ino]
                    or plan.get('baseline_sha') != hashlib.sha256(before.read_bytes()).hexdigest()):
                return False
        attempts = 0
        for entry in path.iterdir():
            match = STARTED.fullmatch(entry.name)
            if match and (entry.is_symlink() or not entry.is_file()
                          or (path / ('rollback-attempt-' + match.group(1) + '.completed')).is_symlink()
                          or not (path / ('rollback-attempt-' + match.group(1) + '.completed')).is_file()
                          or entry.read_text() != 'started\n'
                          or (path / ('rollback-attempt-' + match.group(1) + '.completed')).read_text() != 'ok\n'):
                return False
            if match:
                attempts += 1
            if AFTER_WRITE.fullmatch(entry.name) and (entry.is_symlink() or not entry.is_dir()
                    or (entry / '.migration-attempt-complete').is_symlink()
                    or not (entry / '.migration-attempt-complete').is_file()
                    or (entry / '.migration-attempt-complete').read_text() != 'ok\n'):
                return False
        return attempts > 0 and (path / 'operations.log').read_text().count('退回開始：') == attempts
    except (OSError, ValueError, TypeError):
        return False


def is_zombie(entry):
    try:
        value = (entry / 'stat').read_text()
    except OSError:
        return False
    end = value.rfind(')')
    return end > 0 and value[end + 1:].startswith(' Z ')


def inspectable(proc_root=Path('/proc')):
    """Inspect accessible fds; reject unreadable bd/dolt by comm or argv[0].

    The bd shim runs bd as its owner, using sudo -u for other callers; the
    Dolt user service also executes a normal executable, so their fds are
    expected to be readable. Renamed executables limit the name fallback.
    """
    def unsafe_name(entry):
        comm = (entry / 'comm').read_text().strip()
        command = (entry / 'cmdline').read_bytes().split(b'\0', 1)[0]
        names = (comm, os.fsdecode(command).rsplit('/', 1)[-1])
        return not comm or any(name in ('bd', 'dolt') or name.startswith(('bd-', 'dolt-')) for name in names)

    try:
        mountinfo = (proc_root / 'self/mountinfo').read_text()
        found_proc = False
        for line in mountinfo.splitlines():
            parts = line.split()
            if parts[4] == '/proc':
                found_proc = True
                if any(option.startswith('hidepid=') and option != 'hidepid=0'
                       for option in (parts[5] + ',' + parts[-1]).split(',')):
                    return False
        if not found_proc:
            return False
        for entry in proc_root.iterdir():
            if not entry.name.isdigit():
                continue
            try:
                status = (entry / 'status').read_text()
                lines = [line.split()[1:] for line in status.splitlines() if line.startswith('Uid:')]
                if len(lines) != 1 or len(lines[0]) != 4 or any(not value.isdecimal() for value in lines[0]):
                    return False
                own = os.getuid() in {int(value) for value in lines[0]}
                if not own and unsafe_name(entry):
                    return False
                try:
                    with os.scandir(entry / 'fd') as fds:
                        for fd in fds:
                            try:
                                os.readlink(fd.path)
                            except FileNotFoundError:
                                continue
                except PermissionError:
                    if is_zombie(entry):
                        continue
                    if own and unsafe_name(entry):
                        return False
                    continue
                if not own:
                    continue
                with (entry / 'maps').open() as maps:
                    maps.read(1)
                for name in ('cwd', 'root', 'exe'):
                    try:
                        os.readlink(entry / name)
                    except FileNotFoundError:
                        if entry.exists() and not is_zombie(entry):
                            return False
                        break
            except ProcessLookupError:
                continue
            except FileNotFoundError:
                if entry.exists() and not is_zombie(entry):
                    return False
                continue
            except PermissionError:
                if is_zombie(entry):
                    continue
                return False
            except OSError:
                return False
        return True
    except OSError:
        return False


def in_use(tool, path, allowed_pids=()):
    if Path(tool).name == 'lsof':
        result = subprocess.run([tool, '-t', '+D', str(path)], capture_output=True, text=True, timeout=60)
        if result.returncode == 0:
            if not allowed_pids:
                return True
            if result.stderr or not result.stdout.split() or any(not n.isdecimal() for n in result.stdout.split()):
                raise RuntimeError('lsof 無法確認程序身分')
            return bool({int(n) for n in result.stdout.split()} - set(allowed_pids))
        if result.returncode == 1 and not result.stderr:
            return False
        raise RuntimeError('lsof 無法確認紀錄是否使用中')
    names = [str(path)]
    def walk_error(error):
        raise error
    for directory, dirs, files in os.walk(path, followlinks=False, onerror=walk_error):
        names.extend(str(Path(directory) / name) for name in dirs + files)
    for start in range(0, len(names), 32):
        result = subprocess.run([tool, *names[start:start + 32]], capture_output=True, text=True, timeout=60)
        if result.returncode == 0:
            if not allowed_pids:
                return True
            batch = names[start:start + 32]
            if (not result.stdout.split() or any(not n.isdecimal() for n in result.stdout.split())
                    or any(not any(re.fullmatch(re.escape(name) + r':[A-Za-z ]*', line) for name in batch)
                           for line in result.stderr.splitlines())):
                raise RuntimeError('fuser 無法確認程序身分')
            if {int(n) for n in result.stdout.split()} - set(allowed_pids):
                return True
            continue
        if result.returncode != 1 or result.stderr:
            raise RuntimeError('fuser 無法確認紀錄是否使用中')
    return False


def no_mounts(path):
    """Do not recursively delete an archive containing a mounted filesystem."""
    for line in Path('/proc/self/mountinfo').read_text().splitlines():
        raw = line.split()[4]
        mount = re.sub(r'\\([0-7]{3})', lambda m: chr(int(m.group(1), 8)), raw)
        if mount == str(path) or mount.startswith(str(path) + '/'):
            return False
    return True


def cleanup(state, keep, repo, uid, record=None):
    def emit(message):
        print(message)
        if record is not None:
            record(message)

    if keep < 1 or state.is_symlink() or not state.is_dir():
        raise ValueError('狀態目錄或保留數量不符')
    current = state / 'current'
    if current.is_symlink() or (current.exists() and not current.is_dir()):
        emit('警告：current 不是有效目錄；本批不清理')
        return
    active_complete = False
    if current.is_dir():
        try:
            marker, target, done = (current / name for name in ('.migration-state', 'target.json', 'switch-complete'))
            if all(p.is_file() and not p.is_symlink() for p in (marker, target, done)):
                data = json.loads(target.read_text())
                active_complete = (marker.read_text() == 'migration-state-v1\n' and done.read_text() == 'ok\n'
                                   and data.get('repo') == str(repo) and data.get('uid') == uid)
        except (OSError, ValueError, TypeError):
            emit('警告：current 紀錄無法確認；本批不清理')
            return
    records = sorted((p for p in state.iterdir() if marked(p, repo, uid)),
                     key=lambda p: ((p / 'switch-complete').stat().st_mtime_ns, p.name), reverse=True)
    expired = records[keep - int(active_complete):]
    if not expired:
        return
    tool = shutil.which('fuser') or shutil.which('lsof')
    if not tool or not inspectable() or not shutil.rmtree.avoids_symlink_attacks:
        emit('警告：無法確認紀錄使用狀態；本批不清理')
        return
    removable = []
    try:
        for path in expired:
            if gate_safety.contains_gate(path):
                emit(f'保留含 gate 檔的紀錄 {path}')
            elif not no_mounts(path) or in_use(tool, path):
                emit(f'保留使用中的紀錄 {path}')
            else:
                removable.append((path, path.stat().st_ino))
    except (OSError, RuntimeError, subprocess.SubprocessError) as error:
        emit(f'警告：紀錄使用狀態無法確認；本批不清理：{error}')
        return
    for path, _ in removable:
        emit(f'預計刪除過期紀錄 {path}')
    for path, inode in removable:
        try:
            safe = (marked(path, repo, uid) and path.stat().st_ino == inode
                    and not gate_safety.contains_gate(path) and no_mounts(path) and not in_use(tool, path))
        except (OSError, RuntimeError, subprocess.SubprocessError):
            safe = False
        if not safe:
            emit(f'警告：紀錄狀態改變，停止清理 {path}')
            return
        shutil.rmtree(path)
        emit(f'已刪除過期紀錄 {path}')


def cleanup_safe(state, keep, repo, uid, record=None):
    try:
        cleanup(state, keep, repo, uid, record)
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as error:
        message = f'警告：無法清理舊紀錄；保留剩餘資料：{error}'
        print(message)
        if record is not None:
            try:
                record(message)
            except OSError:
                print('警告：清理紀錄無法寫入')
