from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Protocol
from urllib.parse import urlparse

from app.ai.summarize import SummaryService
from app.services.obsidian_git import ObsidianGitSyncResult
from app.storage.db import Database
from app.utils.links import LinkFetchError, fetch_public_page, find_url
from app.utils.markdown import format_frontmatter, now_stamp, sanitize_filename


PARA_DIRS = [
    "00_Inbox",
    "01_Projects",
    "02_Areas",
    "03_Resources",
    "04_Archive",
    "01_Projects/个人机器人",
    "02_Areas/AI",
    "02_Areas/个人成长",
    "02_Areas/健康",
    "02_Areas/财务",
    "02_Areas/工作",
    "03_Resources/文章",
    "03_Resources/工具",
    "03_Resources/书籍",
    "03_Resources/教程",
]


@dataclass(frozen=True)
class KnowledgeDraft:
    title: str
    raw_content: str
    source_type: str
    source_url: str | None
    para_path: str
    tags: list[str]
    related: list[str]
    summary: str
    key_points: list[str]
    action_items: list[str]


@dataclass(frozen=True)
class KnowledgeNote:
    id: int
    path: Path
    draft: KnowledgeDraft
    git_sync: ObsidianGitSyncResult | None = None


class KnowledgeGitSync(Protocol):
    def sync_note(self, note_path: Path, *, title: str) -> ObsidianGitSyncResult:
        ...


class KnowledgeService:
    def __init__(
        self,
        db: Database,
        vault_path: Path | None,
        summary_service: SummaryService | None = None,
        git_sync: KnowledgeGitSync | None = None,
    ) -> None:
        self.db = db
        self.vault_path = vault_path
        self.summary_service = summary_service
        self.git_sync = git_sync

    def configured(self) -> bool:
        return self.vault_path is not None

    def init_vault(self) -> None:
        if not self.vault_path:
            return
        self.vault_path.mkdir(parents=True, exist_ok=True)
        for dirname in PARA_DIRS:
            (self.vault_path / dirname).mkdir(parents=True, exist_ok=True)

    def capture_text(self, text: str, now: datetime | None = None) -> KnowledgeNote | str | None:
        content = _extract_capture_content(text)
        if not content:
            return None
        draft_or_question = self.build_draft(content, source_type="text", source_url=None, now=now)
        if isinstance(draft_or_question, str):
            return draft_or_question
        return self.write_note(draft_or_question, now=now)

    def capture_link(self, text: str, now: datetime | None = None) -> KnowledgeNote | str | None:
        url = find_url(text)
        if not url:
            return None
        try:
            page = fetch_public_page(url)
        except LinkFetchError as exc:
            return str(exc)

        if self.summary_service:
            summary = self.summary_service.summarize(
                title=page.title,
                content=page.text,
                source_url=page.url,
            )
            draft = KnowledgeDraft(
                title=summary.title or page.title,
                raw_content=page.text,
                source_type="link",
                source_url=page.url,
                para_path=(classify_para(page.text, source_url=page.url) or {"para_path": "03_Resources/文章"})["para_path"],
                tags=summary.tags,
                related=summary.related,
                summary=summary.summary,
                key_points=summary.key_points,
                action_items=summary.action_items,
            )
        else:
            draft_or_question = self.build_draft(page.text, source_type="link", source_url=page.url, now=now)
            if isinstance(draft_or_question, str):
                return draft_or_question
            draft = draft_or_question
        return self.write_note(draft, now=now)

    def build_draft(
        self,
        content: str,
        *,
        source_type: str,
        source_url: str | None,
        now: datetime | None = None,
    ) -> KnowledgeDraft | str:
        classification = classify_para(content, source_url=source_url)
        if classification is None:
            return "这段内容我还不确定该放进哪个知识库目录。你希望放到 Projects、Areas、Resources 还是 Inbox？"

        title = _generate_title(content, source_url=source_url)
        summary = _generate_summary(content)
        key_points = _generate_key_points(content)
        action_items = _generate_action_items(content)
        tags = classification["tags"]
        related = classification["related"]
        return KnowledgeDraft(
            title=title,
            raw_content=content.strip(),
            source_type=source_type,
            source_url=source_url,
            para_path=classification["para_path"],
            tags=tags,
            related=related,
            summary=summary,
            key_points=key_points,
            action_items=action_items,
        )

    def write_note(self, draft: KnowledgeDraft, now: datetime | None = None) -> KnowledgeNote:
        if not self.vault_path:
            raise RuntimeError("OBSIDIAN_VAULT_PATH is not configured")
        self.init_vault()
        now = now or datetime.now()
        filename = f"{now.strftime('%Y-%m-%d')} - {sanitize_filename(draft.title)}.md"
        target_dir = self.vault_path / draft.para_path
        target_dir.mkdir(parents=True, exist_ok=True)
        path = _unique_path(target_dir / filename)
        markdown = render_markdown(draft, now=now)
        path.write_text(markdown, encoding="utf-8")

        relative_path = str(path.relative_to(self.vault_path))
        with self.db.connect() as conn:
            cursor = conn.execute(
                """
                INSERT INTO knowledge_notes (
                    title, source_type, source_url, obsidian_path,
                    tags, related, summary
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    draft.title,
                    draft.source_type,
                    draft.source_url,
                    relative_path,
                    json.dumps(draft.tags, ensure_ascii=False),
                    json.dumps(draft.related, ensure_ascii=False),
                    draft.summary,
                ),
            )
            note_id = int(cursor.lastrowid)
        git_sync_result = self.git_sync.sync_note(path, title=draft.title) if self.git_sync else None
        return KnowledgeNote(id=note_id, path=path, draft=draft, git_sync=git_sync_result)


def handle_knowledge_text(text: str, service: KnowledgeService) -> str | None:
    if not _looks_like_capture(text) and not (_looks_like_link_capture(text) and find_url(text)):
        return None
    if not service.configured():
        return "还没有配置 OBSIDIAN_VAULT_PATH，暂时不能写入 Obsidian。请先在 .env 里配置你的 vault 路径。"

    result = service.capture_link(text) if _looks_like_link_capture(text) and find_url(text) else service.capture_text(text)
    if result is None:
        return None
    if isinstance(result, str):
        return result
    reply = f"已写入 Obsidian 笔记 #{result.id}：{result.path}"
    if result.git_sync:
        if result.git_sync.ok:
            reply = f"{reply}\nGit 同步：{result.git_sync.message}"
        else:
            reply = f"{reply}\nGit 同步失败：{result.git_sync.message}"
    return reply


def render_markdown(draft: KnowledgeDraft, now: datetime | None = None) -> str:
    frontmatter = format_frontmatter(
        {
            "type": _note_type(draft),
            "source_type": draft.source_type,
            "source_url": draft.source_url,
            "created_at": now_stamp(now),
            "tags": draft.tags,
            "related": draft.related,
        }
    )
    key_points = "\n".join(f"- {item}" for item in draft.key_points) or "- 暂无"
    action_items = "\n".join(f"- {item}" for item in draft.action_items) or "- 暂无"
    related = "\n".join(f"- [[{item}]]" for item in draft.related) or "- 暂无"
    return (
        f"{frontmatter}\n\n"
        f"# {draft.title}\n\n"
        f"## 摘要\n\n{draft.summary}\n\n"
        f"## 核心要点\n\n{key_points}\n\n"
        f"## 和我的关系\n\n{related}\n\n"
        f"## 可行动项\n\n{action_items}\n\n"
        f"## 原始来源\n\n{draft.source_url or draft.raw_content}\n"
    )


def classify_para(content: str, source_url: str | None = None) -> dict[str, object] | None:
    text = f"{content} {source_url or ''}".lower()
    if any(keyword in text for keyword in ["个人机器人", "jarvis", "飞书机器人"]):
        return {"para_path": "01_Projects/个人机器人", "tags": ["个人机器人", "AI"], "related": ["个人机器人"]}
    if any(keyword in text for keyword in ["ai", "agent", "openai", "大模型", "人工智能"]):
        return {"para_path": "02_Areas/AI", "tags": ["AI"], "related": ["AI"]}
    if any(keyword in text for keyword in ["财务", "记账", "预算", "报销", "消费"]):
        return {"para_path": "02_Areas/财务", "tags": ["财务"], "related": ["财务"]}
    if any(keyword in text for keyword in ["健康", "运动", "睡眠", "饮食"]):
        return {"para_path": "02_Areas/健康", "tags": ["健康"], "related": ["健康"]}
    if any(keyword in text for keyword in ["工作", "会议", "项目管理", "okr"]):
        return {"para_path": "02_Areas/工作", "tags": ["工作"], "related": ["工作"]}
    if source_url or "http://" in text or "https://" in text or "文章" in content or "教程" in content:
        return {"para_path": "03_Resources/文章", "tags": ["文章"], "related": []}
    if "inbox" in text or "收件箱" in text:
        return {"para_path": "00_Inbox", "tags": ["inbox"], "related": []}
    return None


def _looks_like_capture(text: str) -> bool:
    return any(
        marker in text
        for marker in [
            "整理进知识库",
            "放进知识库",
            "写入知识库",
            "总结这段话",
            "总结一下这段",
            "帮我整理",
            "沉淀成笔记",
        ]
    )


def _looks_like_link_capture(text: str) -> bool:
    return bool(find_url(text)) and any(marker in text for marker in ["总结", "整理", "知识库", "笔记", "链接"])


def _extract_capture_content(text: str) -> str:
    cleaned = text.strip()
    for marker in ["：", ":"]:
        if marker in cleaned:
            prefix, rest = cleaned.split(marker, 1)
            if _looks_like_capture(prefix):
                return rest.strip()
    for phrase in ["整理进知识库", "放进知识库", "写入知识库", "总结这段话", "帮我整理"]:
        cleaned = cleaned.replace(phrase, " ")
    return " ".join(cleaned.split())


def _generate_title(content: str, source_url: str | None = None) -> str:
    if source_url:
        host = urlparse(source_url).netloc or "链接笔记"
        return host
    first_line = content.strip().splitlines()[0] if content.strip() else "知识笔记"
    first_line = re.sub(r"\s+", " ", first_line).strip()
    return first_line[:36] or "知识笔记"


def _generate_summary(content: str) -> str:
    compact = re.sub(r"\s+", " ", content).strip()
    return compact[:180] + ("..." if len(compact) > 180 else "")


def _generate_key_points(content: str) -> list[str]:
    sentences = [item.strip(" 。；;") for item in re.split(r"[。；;\n]", content) if item.strip()]
    return sentences[:5]


def _generate_action_items(content: str) -> list[str]:
    action_markers = ["要", "需要", "应该", "可以", "下一步", "todo", "待办"]
    items = [sentence for sentence in _generate_key_points(content) if any(marker in sentence.lower() for marker in action_markers)]
    return items[:3]


def _note_type(draft: KnowledgeDraft) -> str:
    if draft.para_path.startswith("01_Projects"):
        return "project_note"
    if draft.para_path.startswith("02_Areas"):
        return "area_note"
    if draft.para_path.startswith("03_Resources"):
        return "resource"
    return "capture"


def _unique_path(path: Path) -> Path:
    if not path.exists():
        return path
    stem = path.stem
    suffix = path.suffix
    for index in range(2, 1000):
        candidate = path.with_name(f"{stem} {index}{suffix}")
        if not candidate.exists():
            return candidate
    raise RuntimeError(f"Unable to create unique path for {path}")
