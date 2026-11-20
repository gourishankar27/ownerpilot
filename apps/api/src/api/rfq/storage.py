import hashlib
import re
from pathlib import Path
from typing import Protocol
from uuid import UUID

from .config import settings


class DocumentError(ValueError):
    """Safe, user-visible parser/ingestion error; never includes document text."""


def fingerprint(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def safe_name(name: str) -> str:
    name = name.replace("\\", "/").split("/")[-1]
    return re.sub(r"[^\w. -]", "_", name)[:160] or "document"


class Storage(Protocol):
    def put(self, workspace: str, identifier: str, content: bytes) -> None: ...
    def read(self, workspace: str, identifier: str) -> bytes: ...


class LocalStorage:
    def path(self, workspace: str, identifier: str) -> Path:
        # Only generated UUIDs form paths. Original filenames never do.
        return (
            settings().storage_root.resolve()
            / str(UUID(workspace))
            / str(UUID(identifier))
        )

    def put(self, workspace: str, identifier: str, content: bytes) -> None:
        target = self.path(workspace, identifier)
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open("xb") as stream:
            stream.write(content)

    def read(self, workspace: str, identifier: str) -> bytes:
        return self.path(workspace, identifier).read_bytes()
