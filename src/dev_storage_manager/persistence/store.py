import json
import sqlite3
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from dev_storage_manager.domain.models import Result, Folder, Issue, Candidate, ProjectEvidence


class Store:
    def __init__(self, directory: Path):
        directory.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(directory / "analysis.sqlite3")
        self.db.execute("CREATE TABLE IF NOT EXISTS projects (path TEXT PRIMARY KEY, updated TEXT, status TEXT, result TEXT)")
        self.db.execute("CREATE TABLE IF NOT EXISTS exclusions (project TEXT PRIMARY KEY, paths TEXT NOT NULL)")
        self.db.execute("UPDATE projects SET status='interrupted' WHERE status='running'")
        self.db.commit()

    def projects(self):
        return self.db.execute("SELECT path, updated, status FROM projects ORDER BY path").fetchall()

    def add(self, path):
        self.db.execute("INSERT OR IGNORE INTO projects(path,status) VALUES (?, 'new')", (path,))
        self.db.commit()

    def remove(self, path):
        self.db.execute("DELETE FROM projects WHERE path=?", (path,))
        self.db.execute("DELETE FROM exclusions WHERE project=?", (path,))
        self.db.commit()

    def status(self, path, status):
        self.db.execute("UPDATE projects SET status=? WHERE path=?", (status, path))
        self.db.commit()

    def save(self, result: Result):
        self.db.execute("UPDATE projects SET updated=?, status=?, result=? WHERE path=?",
                        (datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds"),
                         result.status, json.dumps(asdict(result), ensure_ascii=False), result.root))
        self.db.commit()

    def load(self, path):
        row = self.db.execute("SELECT result FROM projects WHERE path=?", (path,)).fetchone()
        if not row or not row[0]:
            return None
        data = json.loads(row[0])
        data["folders"] = [Folder(**x) for x in data["folders"]]
        data["issues"] = [Issue(**x) for x in data["issues"]]
        data["projects"] = [ProjectEvidence(**x) for x in data.get("projects", [])]
        data["candidates"] = [Candidate(**x) for x in data.get("candidates", [])]
        return Result(**data)

    def exclusions(self, path):
        row = self.db.execute("SELECT paths FROM exclusions WHERE project=?", (path,)).fetchone()
        return json.loads(row[0]) if row else []

    def set_exclusions(self, path, paths):
        from pathlib import Path
        for value in paths:
            p = Path(value)
            if p.is_absolute() or p.anchor or ".." in p.parts or not p.parts:
                raise ValueError("제외 경로는 프로젝트 내부 상대 경로여야 합니다.")
        self.db.execute("INSERT OR REPLACE INTO exclusions VALUES (?,?)", (path, json.dumps(paths)))
        self.db.commit()

    def close(self):
        self.db.close()
