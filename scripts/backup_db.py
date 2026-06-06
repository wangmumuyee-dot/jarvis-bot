from __future__ import annotations

from datetime import datetime
from pathlib import Path
import shutil
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.config import get_settings


def main() -> None:
    settings = get_settings()
    source = settings.database_path
    if not source.exists():
        raise SystemExit(f"Database not found: {source}")
    backup_dir = source.parent / "backups"
    backup_dir.mkdir(parents=True, exist_ok=True)
    target = backup_dir / f"{source.stem}-{datetime.now().strftime('%Y%m%d-%H%M%S')}{source.suffix}"
    shutil.copy2(source, target)
    print(f"Backed up database to {target}")


if __name__ == "__main__":
    main()

