from __future__ import annotations

from datetime import datetime
from pathlib import Path
import subprocess
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.config import get_settings


def main() -> None:
    settings = get_settings()
    vault_path = settings.obsidian_vault_path
    if not vault_path:
        raise SystemExit("OBSIDIAN_VAULT_PATH is not configured")
    if not vault_path.exists():
        raise SystemExit(f"Obsidian vault path does not exist: {vault_path}")
    if not _is_git_repo(vault_path):
        raise SystemExit(f"Obsidian vault is not a Git repo: {vault_path}")

    status = _run(["git", "-C", str(vault_path), "status", "--porcelain"])
    if status.returncode != 0:
        raise SystemExit(status.stderr.strip() or status.stdout.strip())
    if not status.stdout.strip():
        print("No Obsidian changes to sync.")
        return

    _check(_run(["git", "-C", str(vault_path), "add", "."]), "git add failed")
    commit_message = f"Sync Jarvis Obsidian notes {datetime.now().strftime('%Y-%m-%d %H:%M')}"
    commit = _run(["git", "-C", str(vault_path), "commit", "-m", commit_message])
    if commit.returncode != 0:
        raise SystemExit(f"git commit failed: {commit.stderr.strip() or commit.stdout.strip()}")

    if settings.obsidian_git_push_enabled:
        _check(_run(["git", "-C", str(vault_path), "push"]), "git push failed")
        print("Synced Obsidian changes and pushed to remote.")
    else:
        print("Committed Obsidian changes. Push is disabled.")


def _is_git_repo(path: Path) -> bool:
    result = _run(["git", "-C", str(path), "rev-parse", "--is-inside-work-tree"])
    return result.returncode == 0 and result.stdout.strip() == "true"


def _check(result: subprocess.CompletedProcess[str], label: str) -> None:
    if result.returncode != 0:
        raise SystemExit(f"{label}: {result.stderr.strip() or result.stdout.strip()}")


def _run(args: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(args, capture_output=True, text=True, timeout=60, check=False)


if __name__ == "__main__":
    main()
