from __future__ import annotations

import tempfile
import unittest
from datetime import datetime
from pathlib import Path

from app.services.knowledge import KnowledgeDraft, KnowledgeService, handle_knowledge_text
from app.services.obsidian_git import ObsidianGitSyncResult
from app.storage.db import Database


class KnowledgeServiceTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.vault = Path(self.tmp.name) / "vault"
        self.db = Database(Path(self.tmp.name) / "jarvis.db")
        self.db.init()
        self.service = KnowledgeService(self.db, self.vault)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_init_para_dirs(self) -> None:
        self.service.init_vault()
        self.assertTrue((self.vault / "00_Inbox").is_dir())
        self.assertTrue((self.vault / "01_Projects" / "个人机器人").is_dir())
        self.assertTrue((self.vault / "02_Areas" / "AI").is_dir())
        self.assertTrue((self.vault / "03_Resources" / "文章").is_dir())

    def test_capture_text_writes_markdown_and_db_record(self) -> None:
        reply = handle_knowledge_text(
            "整理进知识库：个人机器人应该先支持飞书入口，并用 AI 辅助 PARA 分类。",
            self.service,
        )
        assert reply is not None
        self.assertIn("已写入 Obsidian 笔记", reply)
        files = list(self.vault.rglob("*.md"))
        self.assertEqual(len(files), 1)
        content = files[0].read_text(encoding="utf-8")
        self.assertIn("---", content)
        self.assertIn("## 摘要", content)
        self.assertIn("## 核心要点", content)
        self.assertIn("## 可行动项", content)
        self.assertIn("个人机器人", str(files[0]))

    def test_uncertain_classification_asks_clarifying_question(self) -> None:
        reply = handle_knowledge_text("整理进知识库：随手记录一个没有明显分类的句子", self.service)
        assert reply is not None
        self.assertIn("不确定该放进哪个知识库目录", reply)

    def test_markdown_filename_is_sanitized(self) -> None:
        note = self.service.write_note(
            KnowledgeDraft(
                title='AI/Agent: "分类"?',
                raw_content="AI agent 可以帮助整理知识库。",
                source_type="text",
                source_url=None,
                para_path="02_Areas/AI",
                tags=["AI"],
                related=["AI"],
                summary="AI agent 可以帮助整理知识库。",
                key_points=["AI agent 可以帮助整理知识库"],
                action_items=["可以帮助整理知识库"],
            ),
            now=datetime(2026, 6, 3, 12, 0),
        )
        self.assertTrue(note.path.exists())
        self.assertNotIn("/", note.path.name)

    def test_git_sync_runs_after_note_write(self) -> None:
        git_sync = FakeGitSync()
        service = KnowledgeService(self.db, self.vault, git_sync=git_sync)
        reply = handle_knowledge_text(
            "整理进知识库：个人机器人应该先支持飞书入口，并用 AI 辅助 PARA 分类。",
            service,
        )

        assert reply is not None
        self.assertEqual(len(git_sync.synced), 1)
        self.assertIn("Git 同步：synced", reply)


class FakeGitSync:
    def __init__(self) -> None:
        self.synced: list[Path] = []

    def sync_note(self, note_path: Path, *, title: str) -> ObsidianGitSyncResult:
        self.synced.append(note_path)
        return ObsidianGitSyncResult(True, "synced")


if __name__ == "__main__":
    unittest.main()
