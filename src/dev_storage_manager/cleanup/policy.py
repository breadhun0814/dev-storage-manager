"""Conservative cache content checks. Does not perform any file operations."""
from dev_storage_manager.i18n import tr
import hashlib
import importlib.util
import json
import os
import re
import stat
from datetime import datetime
from pathlib import Path

from dev_storage_manager.cleanup.review import Review
from dev_storage_manager.platform.guard import directory_guard
from dev_storage_manager.scanning.scanner import is_link
from dev_storage_manager.scanning.fingerprint import identity
from dev_storage_manager.platform.path_safety import native

MAX_METADATA_BYTES = 8 * 1024 * 1024
PYTEST_TAG = b"Signature: 8a477f597d28d172789f06886806bc55"
PYTEST_README = (b"# pytest cache directory #\n\n"
                 b"This directory contains data from the pytest's cache plugin,\n"
                 b"which provides the `--lf` and `--ff` options, as well as the `cache` fixture.\n\n"
                 b"**Do not** commit this to version control.\n\n"
                 b"See [the docs](https://docs.pytest.org/en/stable/how-to/cache.html) for more information.\n")
PYTEST_TAG_CONTENT = (PYTEST_TAG + b"\n# This file is a cache directory tag created by pytest.\n"
                      b"# For information about cache directory tags, see:\n"
                      b"#\thttps://bford.info/cachedir/spec.html\n")

EXECUTABLE_KINDS = frozenset({"python-cache", "pytest-cache"})


def pytest_json(data: bytes, relative: str):
    def unique_object(pairs):
        value = {}
        for key, item in pairs:
            if key in value:
                raise ValueError(tr("pytest 캐시에 중복 JSON 키가 있습니다."))
            value[key] = item
        return value

    def reject_constant(value):
        raise ValueError(tr("pytest 캐시에 비표준 JSON 숫자가 있습니다."))

    value = json.loads(data, object_pairs_hook=unique_object, parse_constant=reject_constant)
    if relative.endswith("nodeids"):
        valid = isinstance(value, list) and all(isinstance(v, str) for v in value)
    elif relative.endswith("lastfailed"):
        valid = isinstance(value, dict) and all(isinstance(k, str) and v is True for k, v in value.items())
    else:
        valid = (isinstance(value, dict) and set(value) == {"last_failed", "last_test_count", "last_cache_date_str"}
                 and (value["last_failed"] is None or isinstance(value["last_failed"], str))
                 and (value["last_test_count"] is None or (type(value["last_test_count"]) is int and value["last_test_count"] >= 0))
                 and isinstance(value["last_cache_date_str"], str))
        if valid:
            try:
                datetime.fromisoformat(value["last_cache_date_str"])
            except ValueError:
                valid = False
    if not valid:
        raise ValueError(tr("pytest 기본 캐시 JSON 형식이 일치하지 않습니다. 사용자 데이터나 다른 버전의 형식일 수 있습니다."))


def same_open_file(before, opened):
    # CPython 3.12 Windows stat/fstat can expose different ctime semantics.
    # Compare stable handle identity, mode, size, mtime and link count instead.
    fields = ("st_dev", "st_ino", "st_mode", "st_size", "st_mtime_ns", "st_nlink")
    return all(getattr(before, name) == getattr(opened, name) for name in fields)


def read_checked(path: Path, limit=MAX_METADATA_BYTES) -> tuple[bytes, tuple]:
    with directory_guard(path.parent):
        before = os.lstat(native(path))
        if is_link(before) or not stat.S_ISREG(before.st_mode) or before.st_nlink != 1:
            raise ValueError(tr('링크·하드링크 또는 일반 파일이 아닌 항목은 정리 검증할 수 없습니다.'))
        if before.st_size > limit:
            raise ValueError(tr('파일당 내용 검증 한도(8 MiB)를 넘었습니다.'))
        with open(native(path), "rb") as stream:
            opened = os.fstat(stream.fileno())
            if not same_open_file(before, opened):
                raise ValueError(tr('파일을 여는 동안 식별 정보가 변경되었습니다.'))
            data = stream.read(limit + 1)
            if len(data) > limit or not same_open_file(before, os.fstat(stream.fileno())):
                raise ValueError(tr('읽는 동안 파일이 변경되었습니다.'))
        if identity(os.lstat(native(path))) != identity(before):
            raise ValueError(tr('읽은 뒤 파일 식별 정보가 변경되었습니다.'))
        return data, identity(before)


def cache_proof(review: Review, cancel=None) -> dict[str, str]:
    """Return per-cache evidence digests when every included file is recognized.

    Python evidence includes the corresponding source content. Runtime type
    approval and execution-time revalidation are separate required gates.
    This function never changes Candidate.cleanup_supported by itself.
    """
    candidate = review.candidate
    if cancel and cancel.is_set():
        raise ValueError(tr("캐시 내용 검증이 취소되었습니다."))
    target = Path(candidate.path)
    if candidate.kind not in EXECUTABLE_KINDS:
        raise ValueError(tr('가상환경·의존성·빌드 결과 정리는 지원하지 않습니다.'))
    if not review.files:
        raise ValueError(tr('포함 파일이 없는 후보는 정리하지 않습니다.'))
    allowed_directories = {"."} if candidate.kind == "python-cache" else {".", "v", "v/cache"}
    for directory in review.directories:
        if Path(directory).relative_to(target).as_posix() not in allowed_directories:
            raise ValueError(tr('기본 캐시 구조 이외의 하위 폴더가 있습니다.'))
    proof = {}
    relative_names = {str(Path(f.path).relative_to(target)).replace("\\", "/") for f in review.files}
    for included in review.files:
        if cancel and cancel.is_set():
            raise ValueError(tr("캐시 내용 검증이 취소되었습니다."))
        path = Path(included.path)
        relative = path.relative_to(target).as_posix()
        data, _ = read_checked(path)
        if cancel and cancel.is_set():
            raise ValueError(tr("캐시 내용 검증이 취소되었습니다."))
        source_digest = None
        if candidate.kind == "python-cache":
            pattern = re.fullmatch(r"([^/\\]+)\.cpython-312(?:\.opt-[12])?\.pyc", relative)
            if not pattern or len(data) < 16 or data[:4] != importlib.util.MAGIC_NUMBER:
                raise ValueError(tr('Python 3.12 캐시로 검증되지 않은 파일이 포함되어 있습니다: ') + relative)
            flags = int.from_bytes(data[4:8], "little")
            if flags not in (0, 1, 3):
                raise ValueError(tr('지원하지 않는 pyc 헤더입니다.'))
            source = target.parent / (pattern[1] + ".py")
            with directory_guard(source.parent):
                source_info = os.lstat(native(source))
                if is_link(source_info) or not stat.S_ISREG(source_info.st_mode):
                    raise ValueError(tr('대응 .py 원본이 일반 파일이 아닙니다.'))
            source_data, source_identity = read_checked(source)
            if source_identity != identity(source_info):
                raise ValueError(tr("대응 원본을 확인하는 동안 식별 정보가 변경되었습니다."))
            if cancel and cancel.is_set():
                raise ValueError(tr("캐시 내용 검증이 취소되었습니다."))
            source_digest = hashlib.sha256(source_data).digest()
            if flags == 0:
                expected_time = int(source_info.st_mtime) & 0xFFFFFFFF
                if int.from_bytes(data[8:12], "little") != expected_time or int.from_bytes(data[12:16], "little") != (source_info.st_size & 0xFFFFFFFF):
                    raise ValueError(tr('pyc 헤더와 대응 원본의 시각/크기가 일치하지 않습니다.'))
            else:
                if importlib.util.source_hash(source_data) != data[8:16]:
                    raise ValueError(tr('pyc 헤더의 원본 해시가 일치하지 않습니다.'))
        else:
            allowed = {"CACHEDIR.TAG", "README.md", ".gitignore", "v/cache/nodeids", "v/cache/lastfailed", "v/cache/stepwise"}
            if relative not in allowed:
                raise ValueError(tr('pytest 기본 캐시 이외의 파일이 포함되어 있습니다: ') + relative)
            if relative == "CACHEDIR.TAG" and data.replace(b"\r\n", b"\n") != PYTEST_TAG_CONTENT:
                raise ValueError(tr('pytest 캐시 태그 내용이 일치하지 않습니다.'))
            if relative == "README.md" and data.replace(b"\r\n", b"\n") != PYTEST_README:
                raise ValueError(tr('pytest README 내용이 일치하지 않습니다.'))
            if relative == ".gitignore" and data.replace(b"\r\n", b"\n") != b"# Created by pytest automatically.\n*\n":
                raise ValueError(tr('pytest .gitignore 내용이 일치하지 않습니다.'))
            if relative.startswith("v/cache/"):
                pytest_json(data, relative)
        # Bind Python cache evidence to source content too. Timestamp-based pyc
        # headers alone cannot detect same-size edits within one second.
        proof[relative] = (hashlib.sha256(b"pyc-and-source\0" + hashlib.sha256(data).digest() + source_digest).hexdigest()
                           if source_digest is not None else hashlib.sha256(data).hexdigest())
    if candidate.kind == "pytest-cache" and not {"CACHEDIR.TAG", "README.md", ".gitignore"} <= relative_names:
        raise ValueError(tr('필수 pytest 표식이 없습니다.'))
    return proof
