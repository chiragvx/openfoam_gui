import json
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path
from typing import Optional
import re
import config

@dataclass
class Study:
    name: str
    study_id: str = ""          # slug_timestamp, used as filename stem
    created: str = ""
    modified: str = ""
    description: str = ""
    geometry_path: Optional[str] = None
    case_dir: Optional[str] = None
    conditions: dict = field(default_factory=dict)
    mesh_settings: dict = field(default_factory=dict)
    solver_settings: dict = field(default_factory=dict)
    results: dict = field(default_factory=dict)
    ui_state: dict = field(default_factory=dict)

    def __post_init__(self):
        now = datetime.now().isoformat(timespec="seconds")
        if not self.created:
            self.created = now
        if not self.modified:
            self.modified = now
        if not self.study_id:
            slug = re.sub(r"[^a-z0-9]+", "_", self.name.lower()).strip("_")[:32]
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            self.study_id = f"{slug}_{ts}"

class StudyManager:
    @staticmethod
    def _dir() -> Path:
        d = config.STUDIES_DIR
        d.mkdir(parents=True, exist_ok=True)
        return d

    @classmethod
    def list_studies(cls) -> list[Study]:
        studies = []
        for p in sorted(cls._dir().glob("*.json"), key=lambda x: x.stat().st_mtime, reverse=True):
            try:
                studies.append(cls._load_file(p))
            except Exception:
                pass
        return studies

    @classmethod
    def save(cls, study: Study) -> Path:
        study.modified = datetime.now().isoformat(timespec="seconds")
        path = cls._dir() / f"{study.study_id}.json"
        path.write_text(json.dumps(asdict(study), indent=2), encoding="utf-8")
        return path

    @classmethod
    def load(cls, study_id: str) -> Study:
        return cls._load_file(cls._dir() / f"{study_id}.json")

    @classmethod
    def delete(cls, study_id: str) -> None:
        p = cls._dir() / f"{study_id}.json"
        if p.exists():
            p.unlink()

    @staticmethod
    def _load_file(path: Path) -> Study:
        data = json.loads(path.read_text(encoding="utf-8"))
        return Study(**data)
