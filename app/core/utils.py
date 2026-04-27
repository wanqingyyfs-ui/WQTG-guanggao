from __future__ import annotations

from pathlib import Path


def ensure_dir(path: str | Path) -> None:
    Path(path).expanduser().mkdir(parents=True, exist_ok=True)


def safe_text_preview(text: str, max_len: int = 300) -> str:
    if text is None:
        return ""
    value = text.replace("\n", "\\n").replace("\r", "")
    if len(value) <= max_len:
        return value
    return value[:max_len] + "..."


def split_keywords_text(text: str) -> list[str]:
    if not text:
        return []
    parts = [item.strip() for item in text.split(",")]
    return [item for item in parts if item]


def keywords_to_text(keywords: list[str]) -> str:
    return ",".join(keywords)