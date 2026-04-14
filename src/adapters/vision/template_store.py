from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class TemplateRef:
    key: str
    path: str


class TemplateStore:
    def __init__(self, root: str) -> None:
        self._root = Path(root)

    @property
    def root(self) -> Path:
        return self._root

    def resolve(self, key: str, *, profile: str = "default") -> TemplateRef:
        normalized = key.strip().replace("\\", "/")
        if not normalized:
            raise ValueError("template key cannot be empty")
        direct = self._root / normalized
        if direct.exists():
            return TemplateRef(key=key, path=str(direct))

        scoped = self._root / profile / normalized
        if scoped.exists():
            return TemplateRef(key=key, path=str(scoped))

        if "." not in normalized:
            for suffix in (".png", ".jpg", ".jpeg", ".webp"):
                candidate = scoped.with_suffix(suffix)
                if candidate.exists():
                    return TemplateRef(key=key, path=str(candidate))
        raise FileNotFoundError(f"template not found: key={key}, profile={profile}")
