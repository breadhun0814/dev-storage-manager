"""Durable operation journal; independent connections are safe for worker use."""
from dev_storage_manager.i18n import tr
from datetime import datetime, timezone
from dataclasses import dataclass
from pathlib import Path
import sqlite3
import uuid
from dev_storage_manager.domain.cleanup_result import JobResult


class JournalError(RuntimeError):
    """The operation must stop because its durable state cannot be trusted."""


TERMINAL = frozenset({"succeeded", "failed", "unknown", "cancelled"})


class HistoryCancelled(Exception):
    pass


@dataclass
class HistoryPage:
    records: list[tuple]
    moved: dict[str, int]
    total: int
    offset: int
    limit: int
    anchor: int
    query: str
    job: str | None = None


def now():
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


class Journal:
    def __init__(self, directory: Path, read_only=False):
        self.last_job = None
        if read_only:
            self.db = sqlite3.connect((directory / "analysis.sqlite3").absolute().as_uri() + "?mode=ro", uri=True, timeout=0.2)
            self.db.execute("PRAGMA busy_timeout=200")
            return
        directory.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(directory / "analysis.sqlite3", timeout=10)
        self.db.execute("PRAGMA busy_timeout=10000")
        self.db.execute("PRAGMA synchronous=FULL")
        self.db.execute("CREATE TABLE IF NOT EXISTS cleanup_jobs (id TEXT PRIMARY KEY, created TEXT, status TEXT, free_before INTEGER, free_after INTEGER)")
        self.db.execute("CREATE TABLE IF NOT EXISTS cleanup_items (job TEXT, path TEXT, size INTEGER, status TEXT, reason TEXT, destination TEXT, updated TEXT, PRIMARY KEY(job,path))")
        self.db.commit()

    def recover(self):
        self.interrupt()

    def interrupt(self, job=None, reason=None):
        """Recover a stopped job; never infer success from a missing path."""
        with self.db:
            if job is not None and not self.db.execute("SELECT 1 FROM cleanup_jobs WHERE id=?", (job,)).fetchone():
                raise JournalError(tr("중단할 정리 작업 기록이 없습니다."))
            condition, args = (" AND job=?", (job,)) if job is not None else ("", ())
            affected = {row[0] for row in self.db.execute("SELECT DISTINCT job FROM cleanup_items WHERE status IN ('running','pending')" + condition, args)}
            affected.update(row[0] for row in self.db.execute("SELECT id FROM cleanup_jobs WHERE status='running'" + (" AND id=?" if job is not None else ""), args))
            self.db.execute("UPDATE cleanup_items SET status='unknown', reason=?, updated=? WHERE status='running'" + condition,
                            (reason or tr('앱 중단으로 결과 미확정. 원래 경로와 Windows 휴지통을 직접 확인하세요.'), now(), *args))
            self.db.execute("UPDATE cleanup_items SET status='cancelled', reason=?, updated=? WHERE status='pending'" + condition,
                            (tr('실행 전에 작업이 중단되었습니다.'), now(), *args))
            self.db.executemany("UPDATE cleanup_jobs SET status='interrupted' WHERE id=?", [(value,) for value in affected])

    def begin(self, items: list[tuple[str, int]], free_before: int | None):
        if not items or len({p for p, _ in items}) != len(items) or any(not isinstance(p, str) or not p or type(size) is not int or size < 0 for p, size in items):
            raise JournalError(tr("정리 작업의 대상·크기·중복 기록을 확인할 수 없습니다."))
        job = uuid.uuid4().hex
        with self.db:
            self.db.execute("INSERT INTO cleanup_jobs VALUES (?,?, 'running', ?,NULL)", (job, now(), free_before))
            self.db.executemany("INSERT INTO cleanup_items VALUES (?,?,?,'pending','',NULL,?)",
                                [(job, path, size, now()) for path, size in items])
        self.last_job = job
        return job

    def item(self, job, path, status, reason="", destination=None):
        with self.db:
            row = self.db.execute("SELECT i.status,j.status FROM cleanup_items i JOIN cleanup_jobs j ON j.id=i.job WHERE i.job=? AND i.path=?", (job, path)).fetchone()
            allowed = {"pending": {"running", "cancelled"}, "running": TERMINAL}
            if row is None or row[1] != "running" or status not in allowed.get(row[0], set()):
                raise JournalError(tr("정리 대상의 기록 또는 상태 전이를 확인할 수 없어 작업을 중단합니다."))
            if status == "succeeded" and (not isinstance(destination, str) or not destination):
                raise JournalError(tr("휴지통 영수증 경로 없이 성공을 기록할 수 없습니다."))
            changed = self.db.execute("UPDATE cleanup_items SET status=?,reason=?,destination=?,updated=? WHERE job=? AND path=? AND status=? AND EXISTS(SELECT 1 FROM cleanup_jobs WHERE id=? AND status='running')",
                                      (status, reason, destination, now(), job, path, row[0], job))
            if changed.rowcount != 1:
                raise JournalError(tr("정리 대상의 실행 상태를 저장하지 못했습니다."))

    def finish(self, job, status, free_after):
        with self.db:
            states = [row[0] for row in self.db.execute("SELECT status FROM cleanup_items WHERE job=?", (job,))]
            expected = states[0] if states and len(set(states)) == 1 else "partial"
            if not states or any(s not in TERMINAL for s in states) or status != expected:
                raise JournalError(tr("완료되지 않은 항목이 있거나 항목 결과와 작업 결과가 일치하지 않습니다."))
            changed = self.db.execute("UPDATE cleanup_jobs SET status=?,free_after=? WHERE id=? AND status='running'", (status, free_after, job))
            if changed.rowcount != 1:
                raise JournalError(tr("정리 작업 완료 상태를 저장하지 못했습니다."))

    def history(self, include_job_status=False):
        columns = "j.created,i.path,i.size,i.status,i.reason,i.destination,j.free_before,j.free_after,j.id"
        if include_job_status:
            columns += ",j.status"
        return self.db.execute("SELECT " + columns + " FROM cleanup_items i JOIN cleanup_jobs j ON i.job=j.id ORDER BY j.rowid DESC,i.path").fetchall()

    def job_status(self, job):
        row = self.db.execute("SELECT status FROM cleanup_jobs WHERE id=?", (job,)).fetchone()
        if row is None:
            raise JournalError(tr("정리 작업 기록이 없습니다."))
        return row[0]

    def job_result(self, job):
        if self.db.in_transaction:
            raise JournalError(tr("진행 중인 기록 작업과 결과 조회를 같은 연결에서 수행할 수 없습니다."))
        with self.db:
            self.db.execute("BEGIN")
            row = self.db.execute("SELECT created,status,free_before,free_after FROM cleanup_jobs WHERE id=?", (job,)).fetchone()
            if row is None:
                raise JournalError(tr("정리 작업 기록이 없습니다."))
            groups = self.db.execute("SELECT status,COUNT(*),SUM(size),SUM(CASE WHEN typeof(size)!='integer' OR size<0 OR (status='succeeded' AND (destination IS NULL OR typeof(destination)!='text' OR length(destination)=0)) THEN 1 ELSE 0 END) FROM cleanup_items WHERE job=? GROUP BY status", (job,)).fetchall()
            if not groups or any(g[0] not in TERMINAL | {'running', 'pending'} or g[3] for g in groups):
                raise JournalError(tr("정리 결과의 상태·크기·영수증을 확인할 수 없습니다."))
            counts = {g[0]: g[1] for g in groups}
            if (not isinstance(row[0], str) or not row[0] or row[1] not in TERMINAL | {'running', 'partial', 'interrupted'} or
                    any(v is not None and (type(v) is not int or v < 0) for v in row[2:]) or
                    (row[1] in TERMINAL and set(counts) != {row[1]}) or
                    (row[1] == 'partial' and (not set(counts) <= TERMINAL or len(counts) < 2))):
                raise JournalError(tr("전체 작업 상태와 항목 결과를 확인할 수 없습니다."))
            items = self.db.execute("SELECT path,size,status,reason,destination FROM cleanup_items WHERE job=? ORDER BY path LIMIT 200", (job,)).fetchall()
            if any(not isinstance(r[0], str) or not r[0] or any(r[i] is not None and not isinstance(r[i], str) for i in (3, 4)) for r in items):
                raise JournalError(tr("정리 결과의 경로·실패 이유를 확인할 수 없습니다."))
            return JobResult(job, *row, counts, next((g[2] for g in groups if g[0] == 'succeeded'), 0), sum(g[2] for g in groups), items)

    def history_page(self, limit=200, offset=0, anchor=None, query="", cancel=None, job=None):
        """One read snapshot; fixed insertion boundary prevents new-job shifts."""
        if (type(limit) is not int or not 1 <= limit <= 500 or type(offset) is not int or offset < 0 or
                (anchor is not None and (type(anchor) is not int or anchor < 0)) or not isinstance(query, str) or len(query) > 512 or
                (job is not None and (not isinstance(job, str) or not job))):
            raise ValueError(tr("이력 조회 범위 또는 검색어가 올바르지 않습니다."))
        if cancel and cancel.is_set():
            raise HistoryCancelled()
        if self.db.in_transaction:
            raise JournalError(tr("진행 중인 기록 작업과 이력 조회를 같은 연결에서 수행할 수 없습니다."))
        self.db.create_function("dsm_casefold", 1, lambda value: (value or "").casefold(), deterministic=True)
        self.db.set_progress_handler(lambda: int(bool(cancel and cancel.is_set())), 1000)
        try:
            with self.db:
                self.db.execute("BEGIN")
                tables = dict(self.db.execute("SELECT name,type FROM sqlite_master WHERE name IN ('cleanup_jobs','cleanup_items')"))
                if not tables:
                    if job is not None:
                        raise JournalError(tr("정리 작업 기록이 없습니다."))
                    return HistoryPage([], {}, 0, 0, limit, 0, query)
                if len(tables) != 2 or any(value != "table" for value in tables.values()):
                    raise JournalError(tr("정리 이력 테이블의 일부가 없어 조회할 수 없습니다."))
                if anchor is None:
                    anchor = self.db.execute("SELECT COALESCE(MAX(rowid),0) FROM cleanup_jobs").fetchone()[0]
                condition = "j.rowid<=?"
                args = [anchor]
                if job is not None:
                    if not self.db.execute("SELECT 1 FROM cleanup_jobs WHERE id=?", (job,)).fetchone():
                        raise JournalError(tr("정리 작업 기록이 없습니다."))
                    condition += " AND j.id=?"
                    args.append(job)
                if query:
                    condition += " AND (instr(dsm_casefold(i.path),?)>0 OR instr(dsm_casefold(i.reason),?)>0)"
                    args.extend([query.casefold(), query.casefold()])
                source = " FROM cleanup_items i JOIN cleanup_jobs j ON i.job=j.id WHERE " + condition
                total = self.db.execute("SELECT COUNT(*)" + source, args).fetchone()[0]
                offset = min(offset, ((total - 1) // limit) * limit) if total else 0
                records = self.db.execute("SELECT j.created,i.path,i.size,i.status,i.reason,i.destination,j.free_before,j.free_after,j.id,j.status" + source + " ORDER BY j.rowid DESC,i.path LIMIT ? OFFSET ?", [*args, limit, offset]).fetchall()
                for row in records:
                    if (any(not isinstance(row[i], str) or not row[i] for i in (0, 1, 3, 8, 9)) or
                            type(row[2]) is not int or row[2] < 0 or
                            any(row[i] is not None and not isinstance(row[i], str) for i in (4, 5)) or
                            any(row[i] is not None and (type(row[i]) is not int or row[i] < 0) for i in (6, 7))):
                        raise JournalError(tr("이력 데이터의 경로·상태·크기 형식을 확인할 수 없습니다."))
                jobs = list({row[8] for row in records})
                moved = {}
                if jobs:
                    aggregates = self.db.execute("SELECT job,SUM(CASE WHEN status='succeeded' THEN size ELSE 0 END),SUM(CASE WHEN typeof(size)!='integer' OR size<0 THEN 1 ELSE 0 END) FROM cleanup_items WHERE job IN (" + ",".join("?" for _ in jobs) + ") GROUP BY job", jobs).fetchall()
                    if any(row[2] for row in aggregates):
                        raise JournalError(tr("이 작업의 전체 이동 크기를 확인할 수 없습니다."))
                    moved = {row[0]: row[1] for row in aggregates}
                if cancel and cancel.is_set():
                    raise HistoryCancelled()
                return HistoryPage(records, moved, total, offset, limit, anchor, query, job)
        except sqlite3.OperationalError as exc:
            if cancel and cancel.is_set():
                raise HistoryCancelled() from exc
            raise
        finally:
            self.db.set_progress_handler(None, 0)

    def close(self):
        self.db.close()
