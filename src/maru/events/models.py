from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field

from maru.core.models import ArtifactRef, utc_now


class MaruEvent(BaseModel):
    event_id: str = Field(default_factory=lambda: str(uuid4()))
    arc_id: str
    run_id: str | None = None
    timestamp: datetime = Field(default_factory=utc_now)
    source: str
    type: str
    payload: dict[str, Any] = Field(default_factory=dict)
    artifact_refs: list[ArtifactRef] = Field(default_factory=list)
    parent_event_id: str | None = None

