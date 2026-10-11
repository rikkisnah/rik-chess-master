from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from rcm import paths


class Progress:
    """Completed lesson ids, stored in ~/.rik-chess-master/progress.json."""

    def __init__(self, path: Path | None = None):
        self.path = path or paths.progress_path()
        self.completed: set[str] = set()
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            self.completed = set(data.get("completed", []))
        except (OSError, ValueError, AttributeError):
            pass

    def is_done(self, lesson_id: str) -> bool:
        return lesson_id in self.completed

    def mark_done(self, lesson_id: str) -> None:
        self.completed.add(lesson_id)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(
            json.dumps(
                {"completed": sorted(self.completed), "updated": datetime.now().isoformat()},
                indent=2,
            ),
            encoding="utf-8",
        )

    def reset(self) -> None:
        self.completed.clear()
        self.path.unlink(missing_ok=True)
