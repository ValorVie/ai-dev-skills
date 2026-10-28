"""Preserve the metadata inode; callers must first durably save recovery bytes."""
import hashlib
import os
import stat
from pathlib import Path


def sha(data):
    return hashlib.sha256(data).hexdigest()


def write_in_place(path, data, expected_sha=None, expected_identity=None):
    """Rewrite the existing regular file, keeping owner, group, mode and ACL.

    This is not an atomic write.  A caller must save and fsync the original
    bytes and recovery instructions before calling, and must keep bd stopped
    until the write or the recovery is complete.
    """
    fd = os.open(Path(path), os.O_RDWR | os.O_NOFOLLOW)
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode):
            raise ValueError("metadata is not a regular file")
        if expected_identity is not None and [info.st_dev, info.st_ino] != expected_identity:
            raise ValueError("metadata identity changed since it was inspected")
        with os.fdopen(os.dup(fd), "rb") as source:
            original = source.read()
        if expected_sha is not None and sha(original) != expected_sha:
            raise ValueError("metadata changed since it was inspected")
        os.lseek(fd, 0, os.SEEK_SET)
        view = memoryview(data)
        while view:
            written = os.write(fd, view)
            if written <= 0:
                raise OSError("short metadata write")
            view = view[written:]
        os.ftruncate(fd, len(data))
        os.fsync(fd)
        after = os.fstat(fd)
        if (info.st_dev, info.st_ino, info.st_uid, info.st_gid, stat.S_IMODE(info.st_mode)) != (
            after.st_dev, after.st_ino, after.st_uid, after.st_gid, stat.S_IMODE(after.st_mode)
        ):
            raise OSError("metadata identity or permissions changed")
    finally:
        os.close(fd)
