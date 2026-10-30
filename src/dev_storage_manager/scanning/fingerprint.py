import hashlib
import json
import os


def identity(info: os.stat_result) -> tuple:
    return (info.st_dev, info.st_ino, info.st_mode, info.st_size,
            info.st_mtime_ns, info.st_ctime_ns, info.st_nlink,
            getattr(info, "st_file_attributes", 0))


def signature(own: tuple, entries: list[tuple], children: list[tuple]) -> str:
    value = json.dumps([own, sorted(entries), sorted(children)], ensure_ascii=True,
                       separators=(",", ":")).encode("ascii")
    return hashlib.sha256(value).hexdigest()
