from __future__ import annotations

import html
import re
import urllib.error
import urllib.request
from dataclasses import dataclass
from html.parser import HTMLParser


URL_RE = re.compile(r"https?://[^\s，。]+")


@dataclass(frozen=True)
class FetchedPage:
    url: str
    title: str
    text: str


class LinkFetchError(RuntimeError):
    pass


class _ReadableHTMLParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.title_parts: list[str] = []
        self.text_parts: list[str] = []
        self._tag_stack: list[str] = []
        self._skip_depth = 0

    def handle_starttag(self, tag: str, attrs) -> None:
        self._tag_stack.append(tag)
        if tag in {"script", "style", "noscript", "svg"}:
            self._skip_depth += 1
        if tag in {"p", "br", "div", "section", "article", "li", "h1", "h2", "h3"}:
            self.text_parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if self._tag_stack:
            self._tag_stack.pop()
        if tag in {"script", "style", "noscript", "svg"} and self._skip_depth:
            self._skip_depth -= 1
        if tag in {"p", "div", "section", "article", "li", "h1", "h2", "h3"}:
            self.text_parts.append("\n")

    def handle_data(self, data: str) -> None:
        if self._skip_depth:
            return
        current_tag = self._tag_stack[-1] if self._tag_stack else ""
        cleaned = html.unescape(data).strip()
        if not cleaned:
            return
        if current_tag == "title":
            self.title_parts.append(cleaned)
        elif current_tag not in {"meta", "head"}:
            self.text_parts.append(cleaned)

    @property
    def title(self) -> str:
        return normalize_text(" ".join(self.title_parts))[:120]

    @property
    def text(self) -> str:
        lines = [normalize_text(line) for line in "\n".join(self.text_parts).splitlines()]
        lines = [line for line in lines if line]
        return "\n".join(lines)


def find_url(text: str) -> str | None:
    match = URL_RE.search(text)
    return match.group(0).rstrip("，。,.") if match else None


def fetch_public_page(url: str, *, timeout_seconds: int = 10, max_chars: int = 20000) -> FetchedPage:
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 PersonalJarvisBot/0.1",
            "Accept": "text/html,application/xhtml+xml,text/plain;q=0.8,*/*;q=0.5",
        },
        method="GET",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
            content_type = response.headers.get("Content-Type", "")
            raw = response.read(max_chars * 4)
    except urllib.error.URLError as exc:
        raise LinkFetchError(f"链接抓取失败：{exc}") from exc

    charset = _charset_from_content_type(content_type) or "utf-8"
    html_text = raw.decode(charset, errors="replace")
    return extract_page_text(url, html_text, max_chars=max_chars)


def extract_page_text(url: str, html_text: str, *, max_chars: int = 20000) -> FetchedPage:
    parser = _ReadableHTMLParser()
    parser.feed(html_text)
    text = parser.text
    if not text:
        text = normalize_text(re.sub(r"<[^>]+>", " ", html_text))
    text = text[:max_chars]
    title = parser.title or _title_from_text(text) or url
    if len(text) < 30:
        raise LinkFetchError("链接正文太短，可能需要登录或页面不适合抓取。")
    return FetchedPage(url=url, title=title, text=text)


def normalize_text(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def _charset_from_content_type(content_type: str) -> str | None:
    match = re.search(r"charset=([\w-]+)", content_type, re.IGNORECASE)
    return match.group(1) if match else None


def _title_from_text(text: str) -> str:
    return next((line.strip() for line in text.splitlines() if line.strip()), "")[:80]
