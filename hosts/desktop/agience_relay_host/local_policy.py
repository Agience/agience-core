from __future__ import annotations

from pathlib import Path


class LocalPolicy:
    def __init__(self, allowed_roots: tuple[Path, ...]):
        self.allowed_roots = tuple(root.resolve() for root in allowed_roots)

    def resolve_allowed_path(self, raw_path: str) -> Path:
        candidate = Path(raw_path).expanduser().resolve()
        for root in self.allowed_roots:
            if candidate == root or root in candidate.parents:
                return candidate
        allowed = ", ".join(str(root) for root in self.allowed_roots)
        raise PermissionError(f"Path '{candidate}' is outside allowed roots: {allowed}")

    def list_dir(self, raw_path: str) -> list[dict[str, object]]:
        target = self.resolve_allowed_path(raw_path)
        if not target.is_dir():
            raise NotADirectoryError(str(target))
        entries: list[dict[str, object]] = []
        for child in sorted(target.iterdir(), key=lambda item: item.name.lower()):
            entries.append(
                {
                    "name": child.name,
                    "path": str(child),
                    "is_dir": child.is_dir(),
                    "size": child.stat().st_size if child.is_file() else None,
                }
            )
        return entries

    def read_text(self, raw_path: str, max_bytes: int = 65536) -> dict[str, object]:
        target = self.resolve_allowed_path(raw_path)
        if not target.is_file():
            raise FileNotFoundError(str(target))
        data = target.read_bytes()
        truncated = len(data) > max_bytes
        decoded = data[:max_bytes].decode("utf-8", errors="replace")
        return {
            "path": str(target),
            "content": decoded,
            "truncated": truncated,
            "bytes_read": min(len(data), max_bytes),
            "total_bytes": len(data),
        }