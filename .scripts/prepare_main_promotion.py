#!/usr/bin/env python
"""
Generate a promotion note or pull request summary from the current branch.

Usage:
    python .scripts/prepare_main_promotion.py
    python .scripts/prepare_main_promotion.py --mode pr
    python .scripts/prepare_main_promotion.py --base main --head dev/john

Writes a prefilled message file into .git/ and prints the path.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PROMOTION_OUTPUT = ROOT / ".git" / "PROMOTE_MAIN_MSG.txt"
PR_OUTPUT = ROOT / ".git" / "PULL_REQUEST_BODY.md"


def run_git(*args: str) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        message = result.stderr.strip() or result.stdout.strip() or f"git {' '.join(args)} failed"
        raise RuntimeError(message)
    return result.stdout.strip()


def current_branch() -> str:
    return run_git("rev-parse", "--abbrev-ref", "HEAD")


def top_level_areas(files: list[str]) -> list[str]:
    areas: list[str] = []
    for file_path in files:
        clean = file_path.strip()
        if not clean:
            continue
        top = clean.split("/", 1)[0]
        if top not in areas:
            areas.append(top)
    return areas[:8]


def bullet_lines(items: list[str], empty_line: str) -> str:
    if not items:
        return f"- {empty_line}"
    return "\n".join(f"- {item}" for item in items)


def build_promotion_note(base: str, head: str, subjects: list[str], areas: list[str]) -> str:
    summary_subject = f"promote(main): integrate {head}"
    why_default = f"This branch is coherent enough to become the current shared tip from {head}."
    what_default = bullet_lines(subjects[:8], "summarize the main change set")
    affects_default = bullet_lines(areas, "list affected domains or constraints")

    return (
        f"{summary_subject}\n\n"
        f"Why:\n"
        f"{why_default}\n\n"
        f"What:\n"
        f"{what_default}\n\n"
        f"Affects:\n"
        f"{affects_default}\n\n"
        f"Follow-up:\n"
        f"- note anything intentionally deferred\n"
    )


def build_pr_note(base: str, head: str, subjects: list[str], areas: list[str]) -> str:
    summary_lines = subjects[:3]
    summary_text = " ".join(summary_lines).strip() if summary_lines else f"Summarize the change from {head} into {base}."
    what_default = bullet_lines(subjects[:8], "summarize the main change set")
    areas_text = ", ".join(areas) if areas else "list affected domains"

    return (
        "## Summary\n\n"
        f"{summary_text}\n\n"
        "## Classification\n\n"
        "- Type: feat | fix | refactor | docs | test | chore\n"
        f"- Domains affected: {areas_text}\n"
        "- Constraint, behavior, contract, or mixed:\n\n"
        "## Why\n\n"
        f"This change promotes work from `{head}` toward `{base}` because it is coherent enough for review or integration.\n\n"
        "## What Changed\n\n"
        f"{what_default}\n\n"
        "## Validation\n\n"
        "- [ ] Backend checks run if backend changed\n"
        "- [ ] Frontend checks run if frontend changed\n"
        "- [ ] Docs updated if behavior or workflow changed\n"
        "- [ ] No secrets or credentials added\n\n"
        "## Follow-up\n\n"
        "Anything intentionally deferred.\n\n"
        "## Agience Links\n\n"
        "Related cards, specs, reports, issues, or notes.\n"
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", default="main")
    parser.add_argument("--head", default=None)
    parser.add_argument("--mode", choices=["promote", "pr"], default="promote")
    args = parser.parse_args()

    head = args.head or current_branch()
    base = args.base

    if head == base:
        print(f"Current branch is already {base}; run this from your development lane.", file=sys.stderr)
        return 1

    merge_base = run_git("merge-base", base, head)
    subjects_raw = run_git("log", "--reverse", "--pretty=format:%s", f"{merge_base}..{head}")
    files_raw = run_git("diff", "--name-only", f"{merge_base}..{head}")

    subjects = [line.strip() for line in subjects_raw.splitlines() if line.strip()]
    files = [line.strip() for line in files_raw.splitlines() if line.strip()]
    areas = top_level_areas(files)

    if args.mode == "pr":
        body = build_pr_note(base, head, subjects, areas)
        output_path = PR_OUTPUT
    else:
        body = build_promotion_note(base, head, subjects, areas)
        output_path = PROMOTION_OUTPUT

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(body, encoding="utf-8")
    print(output_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())