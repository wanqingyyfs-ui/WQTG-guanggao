from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class BrowserCommand:
    name: str
    payload: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {"name": self.name, "payload": self.payload}


@dataclass(frozen=True)
class BrowserEvent:
    account_id: int
    name: str
    payload: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {"account_id": self.account_id, "name": self.name, "payload": self.payload}
