#!/usr/bin/env python
import argparse
import json
import re
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BUILD_INFO = ROOT / "build_info.json"
SEMVER_RE = re.compile(r"^\d+\.\d+\.\d+(?:-[0-9A-Za-z.-]+)?$")


def read_version() -> str:
	data = json.loads(BUILD_INFO.read_text(encoding="utf-8"))
	version = str(data.get("version", "")).strip()
	if not version:
		raise ValueError("build_info.json must contain a non-empty version")
	if not SEMVER_RE.match(version):
		raise ValueError(f"Unsupported version format: {version}")
	return version


def run_git(*args: str, capture: bool = False) -> str:
	result = subprocess.run(
		["git", *args],
		cwd=ROOT,
		check=True,
		text=True,
		capture_output=capture,
	)
	return result.stdout.strip() if capture else ""


def main() -> int:
	parser = argparse.ArgumentParser(description="Create a local git tag that matches build_info.json.")
	parser.add_argument("--create", action="store_true", help="Create the local annotated git tag.")
	parser.add_argument("--push", action="store_true", help="Print the git push command after creating the tag.")
	parser.add_argument("--message", help="Optional annotated tag message.")
	args = parser.parse_args()

	try:
		version = read_version()
	except Exception as exc:
		print(f"ERROR: {exc}", file=sys.stderr)
		return 1

	if "-" in version:
		print(
			"ERROR: build_info.json contains a prerelease version. Prereleases publish from release/* branches; only stable versions may be tagged.",
			file=sys.stderr,
		)
		return 1

	tag = f"v{version}"
	message = args.message or f"Release {tag}"

	try:
		current_branch = run_git("branch", "--show-current", capture=True)
		current_commit = run_git("rev-parse", "--short", "HEAD", capture=True)
		existing = run_git("tag", "-l", tag, capture=True)
	except subprocess.CalledProcessError as exc:
		print(f"ERROR: git command failed: {exc}", file=sys.stderr)
		return 1

	print(f"Version: {version}")
	print(f"Tag: {tag}")
	print(f"Branch: {current_branch or '(detached HEAD)'}")
	print(f"Commit: {current_commit}")

	if existing:
		print(f"ERROR: tag {tag} already exists locally.", file=sys.stderr)
		return 1

	if not args.create:
		print("")
		print("Preview only. No tag created.")
		print(f"To create locally: git tag -a {tag} -m \"{message}\"")
		print(f"To push later:     git push origin {tag}")
		return 0

	try:
		run_git("tag", "-a", tag, "-m", message)
	except subprocess.CalledProcessError as exc:
		print(f"ERROR: failed to create tag {tag}: {exc}", file=sys.stderr)
		return 1

	print("")
	print(f"Created local tag {tag}")
	if args.push:
		print(f"Push with: git push origin {tag}")
	return 0


if __name__ == "__main__":
	raise SystemExit(main())
