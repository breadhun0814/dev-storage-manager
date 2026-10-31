from dev_storage_manager.i18n import tr
import json
import hashlib
import sqlite3
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from dev_storage_manager.domain.models import Result, Folder, Issue, Candidate, ProjectEvidence, FileSummary


class Store:
    def __init__(self, directory: Path, recover_running: bool = True):
        self.directory = directory
        directory.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(directory / "analysis.sqlite3")
        self.db.execute("CREATE TABLE IF NOT EXISTS projects (path TEXT PRIMARY KEY, updated TEXT, status TEXT, result TEXT)")
        if "logical_size" not in {row[1] for row in self.db.execute("PRAGMA table_info(projects)")}:
            self.db.execute("ALTER TABLE projects ADD COLUMN logical_size INTEGER")
        self.db.execute("CREATE TABLE IF NOT EXISTS exclusions (project TEXT PRIMARY KEY, paths TEXT NOT NULL)")
        self.db.execute("CREATE TABLE IF NOT EXISTS previous_results (project TEXT PRIMARY KEY, result TEXT NOT NULL)")
        self.db.execute("CREATE TABLE IF NOT EXISTS file_samples (project TEXT PRIMARY KEY, analysis_hash TEXT NOT NULL, result TEXT NOT NULL)")
        if recover_running:
            self.db.execute("UPDATE projects SET status='interrupted' WHERE status='running'")
        self.db.commit()

    def projects(self):
        return self.db.execute("SELECT path, updated, status FROM projects ORDER BY path").fetchall()

    def project_summaries(self):
        return self.db.execute("SELECT path, updated, status, logical_size FROM projects ORDER BY path").fetchall()

    def add(self, path):
        self.db.execute("INSERT OR IGNORE INTO projects(path,status) VALUES (?, 'new')", (path,))
        self.db.commit()

    def remove(self, path):
        self.db.execute("DELETE FROM projects WHERE path=?", (path,))
        self.db.execute("DELETE FROM exclusions WHERE project=?", (path,))
        self.db.execute("DELETE FROM previous_results WHERE project=?", (path,))
        self.db.execute("DELETE FROM file_samples WHERE project=?", (path,))
        self.db.commit()

    def status(self, path, status):
        self.db.execute("UPDATE projects SET status=? WHERE path=?", (status, path))
        self.db.commit()

    def save(self, result: Result):
        data = asdict(result)
        sample = {key: data.pop(key) for key in ("largest_files", "file_sample_available", "file_sample_limit")}
        # Keep the base payload readable by released 0.6.x applications.
        # Old apps may rewrite it, so bind the optional sample to its exact hash.
        payload = json.dumps(data, ensure_ascii=False)
        digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()
        with self.db:
            previous = self.db.execute("SELECT result FROM projects WHERE path=?", (result.root,)).fetchone()
            if previous and previous[0] and json.loads(previous[0]).get("status", "complete") == "complete":
                self.db.execute("INSERT OR REPLACE INTO previous_results VALUES (?,?)", (result.root, previous[0]))
            self.db.execute("UPDATE projects SET updated=?, status=?, result=?, logical_size=? WHERE path=?",
                        (datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds"),
                         result.status, payload, result.size, result.root))
            self.db.execute("INSERT OR REPLACE INTO file_samples VALUES (?,?,?)",
                            (result.root, digest, json.dumps(sample, ensure_ascii=False)))

    def load(self, path):
        row = self.db.execute("SELECT result FROM projects WHERE path=?", (path,)).fetchone()
        if not row or not row[0]:
            return None
        result = self.decode(row[0])
        sample = self.db.execute("SELECT analysis_hash, result FROM file_samples WHERE project=?", (path,)).fetchone()
        if sample and sample[0] == hashlib.sha256(row[0].encode("utf-8")).hexdigest():
            try:
                metadata = json.loads(sample[1])
                limit = metadata["file_sample_limit"]
                if type(limit) is not int or not 1 <= limit <= 500 or not isinstance(metadata["largest_files"], list) or len(metadata["largest_files"]) > limit:
                    raise ValueError("Invalid file sample bounds")
                files = [FileSummary(**x) for x in metadata["largest_files"]]
                if any(not isinstance(f.path, str) or type(f.size) is not int or f.size < 0 for f in files) or type(metadata["file_sample_available"]) is not bool:
                    raise ValueError("Invalid file sample record")
                result.largest_files = files
                result.file_sample_available = metadata["file_sample_available"]
                result.file_sample_limit = limit
            except (ValueError, KeyError, TypeError, AttributeError, RecursionError):
                # Optional detail corruption must not hide a usable base analysis.
                result.largest_files = []
                result.file_sample_available = False
        return result

    def has_result(self, path):
        row = self.db.execute("SELECT result IS NOT NULL FROM projects WHERE path=?", (path,)).fetchone()
        return bool(row and row[0])

    @staticmethod
    def decode(value):
        data = json.loads(value)
        data["folders"] = [Folder(**x) for x in data["folders"]]
        data["issues"] = [Issue(**x) for x in data["issues"]]
        data["projects"] = [ProjectEvidence(**x) for x in data.get("projects", [])]
        data["candidates"] = [Candidate(**x) for x in data.get("candidates", [])]
        data["largest_files"] = [FileSummary(**x) for x in data.get("largest_files", [])]
        return Result(**data)

    def previous(self, path):
        row = self.db.execute("SELECT result FROM previous_results WHERE project=?", (path,)).fetchone()
        return self.decode(row[0]) if row else None

    def exclusions(self, path):
        row = self.db.execute("SELECT paths FROM exclusions WHERE project=?", (path,)).fetchone()
        return json.loads(row[0]) if row else []

    def set_exclusions(self, path, paths):
        from pathlib import Path
        for value in paths:
            p = Path(value)
            if p.is_absolute() or p.anchor or ".." in p.parts or not p.parts:
                raise ValueError(tr('제외 경로는 프로젝트 내부 상대 경로여야 합니다.'))
        self.db.execute("INSERT OR REPLACE INTO exclusions VALUES (?,?)", (path, json.dumps(paths)))
        self.db.commit()

    def close(self):
        self.db.close()
