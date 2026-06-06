from __future__ import annotations

import subprocess
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path


@dataclass(frozen=True)
class ObsidianGitSyncResult:
    ok: bool
    message: str


class ObsidianGitSync:
    def __init__(self, vault_path: Path, *, push_enabled: bool = True) -> None:
        self.vault_path = vault_path
        self.push_enabled = push_enabled

    def sync_note(self, note_path: Path, *, title: str) -> ObsidianGitSyncResult:
        if not self._is_git_repo():
            return ObsidianGitSyncResult(False, f"Obsidian vault 不是 Git 仓库：{self.vault_path}")

        relative_path = note_path.relative_to(self.vault_path)
        add = self._run(["git", "-C", str(self.vault_path), "add", str(relative_path)])
        if add.returncode != 0:
            return ObsidianGitSyncResult(False, f"git add 失败：{add.stderr.strip() or add.stdout.strip()}")

        diff = self._run(["git", "-C", str(self.vault_path), "diff", "--cached", "--quiet"])
        if diff.returncode == 0:
            return ObsidianGitSyncResult(True, "没有新的 Obsidian 变更需要提交")
        if diff.returncode not in {0, 1}:
            return ObsidianGitSyncResult(False, f"git diff 检查失败：{diff.stderr.strip() or diff.stdout.strip()}")

        commit_message = f"Add Jarvis note: {title[:60]} ({datetime.now().strftime('%Y-%m-%d %H:%M')})"
        commit = self._run(["git", "-C", str(self.vault_path), "commit", "-m", commit_message])
        if commit.returncode != 0:
            return ObsidianGitSyncResult(False, f"git commit 失败：{commit.stderr.strip() or commit.stdout.strip()}")

        if not self.push_enabled:
            return ObsidianGitSyncResult(True, "Obsidian 笔记已提交，未自动 push")

        push = self._run(["git", "-C", str(self.vault_path), "push"])
        if push.returncode != 0:
            return ObsidianGitSyncResult(False, f"git push 失败：{push.stderr.strip() or push.stdout.strip()}")
        return ObsidianGitSyncResult(True, "Obsidian 笔记已提交并 push 到 Git 仓库")

    def _is_git_repo(self) -> bool:
        result = self._run(["git", "-C", str(self.vault_path), "rev-parse", "--is-inside-work-tree"])
        return result.returncode == 0 and result.stdout.strip() == "true"

    @staticmethod
    def _run(args: list[str]) -> subprocess.CompletedProcess[str]:
        return subprocess.run(args, capture_output=True, text=True, timeout=30, check=False)
