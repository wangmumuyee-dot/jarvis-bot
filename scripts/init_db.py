from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.config import get_settings
from app.storage.db import Database


def main() -> None:
    settings = get_settings()
    db = Database(settings.database_path)
    db.init()
    print(f"Initialized database at {settings.database_path}")


if __name__ == "__main__":
    main()
