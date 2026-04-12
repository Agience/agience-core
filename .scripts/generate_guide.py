#!/usr/bin/env python3
"""
Generate `docs/guide/guide.json` from existing markdown in `docs/`.

This script scans `docs/*.md` and key subfolders like `docs/features/`
and `docs/use-cases/`
for H2 sections and builds a curated, end‑user‑focused guide dataset suitable for
fast import by the demo data agent.

Usage (from repo root):
    python .scripts/generate_guide.py

Optional env:
  MAX_CARDS=16   # limit number of cards in the generated guide

Notes:
- This is a heuristic exporter (no LLM). Tweak selection logic as needed.
- The demo agent will automatically use `docs/guide/guide.json` when present.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Dict, List
import re

BASE = Path(__file__).resolve().parents[1]
DOCS = BASE / ".docs" / "corpus"
GUIDE_DIR = DOCS / "guide"
GUIDE_FILE = GUIDE_DIR / "guide.json"

MAX_CARDS = int(os.getenv("MAX_CARDS", "16"))

PRIORITY_SOURCES = [
    ("overview", DOCS / "README.md"),
]
PRIORITY_DIRS = [
    ("features", DOCS / "features"),
    ("use-cases", DOCS / "use-cases"),
]


def strip_front_matter(md: str) -> str:
    if md.startswith("---"):
        delimiter = "\n---"
        end = md.find(delimiter, 3)
        if end != -1:
            return md[end + len(delimiter):].lstrip("\r\n")
    return md


def sectionize_markdown(md: str) -> List[Dict[str, str]]:
    text = strip_front_matter(md).replace("\r\n", "\n").replace("\r", "\n")
    sections: List[Dict[str, str]] = []
    h1_match = re.search(r"(?m)^#\s+(.+)$", text)
    start_idx = h1_match.end() if h1_match else 0
    h2_iter = list(re.finditer(r"(?m)^##\s+(.+)$", text))

    if h2_iter:
        preamble = text[start_idx:h2_iter[0].start()].strip()
        if preamble:
            sections.append({"title": "Overview", "body": preamble})
        for idx, match in enumerate(h2_iter):
            title = match.group(1).strip()
            body_start = match.end()
            body_end = h2_iter[idx + 1].start() if idx + 1 < len(h2_iter) else len(text)
            body = text[body_start:body_end].strip()
            if title and body:
                sections.append({"title": title, "body": body})
    else:
        body = text[start_idx:].strip()
        if body:
            sections.append({
                "title": h1_match.group(1).strip() if h1_match else "Guide",
                "body": body,
            })
    return sections


def first_paragraph(md: str) -> str:
    parts = [p.strip() for p in re.split(r"\n\s*\n", md or "") if p.strip()]
    if not parts:
        return ""
    para = re.sub(r"^#+\s+", "", parts[0])
    para = para.replace("`", "")
    return para[:240] + ("..." if len(para) > 240 else "")


def curate_sections() -> List[Dict[str, Any]]:
    sections_raw: List[Dict[str, Any]] = []

    def read_sections(path: Path, category: str) -> List[Dict[str, Any]]:
        out: List[Dict[str, Any]] = []
        try:
            text = path.read_text(encoding="utf-8")
        except Exception:
            return out
        for order, sec in enumerate(sectionize_markdown(text), start=1):
            out.append({
                "title": sec["title"],
                "body": sec["body"],
                "category": category,
                "path": str(path.relative_to(DOCS)) if DOCS in path.parents or path == DOCS else path.name,
                "order": order,
            })
        return out

    if DOCS.exists():
        for cat, fp in PRIORITY_SOURCES:
            if fp.is_file():
                sections_raw.extend(read_sections(fp, cat))
        for cat, dp in PRIORITY_DIRS:
            if dp.is_dir():
                for md in sorted(dp.rglob("*.md")):
                    if md.name.startswith("_"):
                        continue
                    sections_raw.extend(read_sections(md, cat))

    # Curate: prioritize overview/help/features, cap by MAX_CARDS
    cat_rank = {"overview": 0, "help": 1, "features": 2, "use-cases": 3}
    sections_sorted = sorted(
        sections_raw,
        key=lambda s: (
            cat_rank.get(str(s.get("category") or "docs"), 99),
            str(s.get("path", "")),
            s.get("order", 0),
        ),
    )

    curated: List[Dict[str, Any]] = []
    seen_titles: set[str] = set()
    for sec in sections_sorted:
        if len(curated) >= MAX_CARDS:
            break
        title = (sec.get("title") or "").strip()
        body = (sec.get("body") or "").strip()
        if not title or not body:
            continue
        if title.lower() in seen_titles:
            continue
        seen_titles.add(title.lower())
        desc = first_paragraph(body)
        tags = ["guide", str(sec.get("category") or "docs")]
        curated.append({
            "title": f"Guide: {title}" if not title.lower().startswith("guide:") else title,
            "description": desc or "Agience guide topic",
            "content": body,
            "tags": tags,
            "metadata": {
                "category": str(sec.get("category") or "docs"),
                "doc_path": str(sec.get("path") or "docs"),
                "section_order": sec.get("order"),
            },
        })
    return curated


def main() -> None:
    GUIDE_DIR.mkdir(parents=True, exist_ok=True)
    cards = curate_sections()
    data = {
        "collection": {
            "name": "Agience Guide",
            "description": "A practical, end‑user guide to Agience. Short, actionable tips to get you productive fast."
        },
        "workspace": {"name": "Agience Guide"},
        "cards": cards,
    }
    GUIDE_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Wrote {len(cards)} cards to {GUIDE_FILE}")


if __name__ == "__main__":
    main()
