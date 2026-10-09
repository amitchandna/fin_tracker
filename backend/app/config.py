"""Runtime configuration, read from environment variables."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]


@dataclass(frozen=True)
class Settings:
    data_dir: Path
    state_dir: Path
    frontend_dist: Path

    @classmethod
    def from_env(cls) -> "Settings":
        data_dir = Path(os.environ.get("FIN_TRACKER_DATA_DIR", REPO_ROOT / "data")).expanduser().resolve()
        state_dir = Path(os.environ.get("FIN_TRACKER_STATE_DIR", data_dir / ".fintracker")).expanduser().resolve()
        frontend_dist = Path(os.environ.get("FIN_TRACKER_FRONTEND_DIST", REPO_ROOT / "frontend" / "dist"))
        return cls(data_dir=data_dir, state_dir=state_dir, frontend_dist=frontend_dist)
