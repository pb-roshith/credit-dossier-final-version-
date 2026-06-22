"""
MistralAgent model — persists Mistral agent IDs per deal+section.

Each deal gets 16 agents (one per section), created via Mistral Agents API.
Agent IDs are stored here for reuse across generation calls.
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import String, DateTime, ForeignKey, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


def _now() -> datetime:
    return datetime.now(timezone.utc)


class MistralAgent(Base):
    """A Mistral agent created for a specific deal section."""

    __tablename__ = "mistral_agents"

    id: Mapped[str] = mapped_column(
        String(64), primary_key=True,
        default=lambda: "ma_" + uuid.uuid4().hex[:8],
    )
    deal_id: Mapped[str] = mapped_column(
        ForeignKey("deals.id", ondelete="CASCADE"), nullable=False,
    )
    section_key: Mapped[str] = mapped_column(String(64), nullable=False)
    agent_id: Mapped[str] = mapped_column(String(256), nullable=False)  # Mistral's agent ID
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now,
    )

    __table_args__ = (
        UniqueConstraint("deal_id", "section_key", name="uq_deal_section_agent"),
    )

    # Relationships
    deal: Mapped["Deal"] = relationship(back_populates="mistral_agents")  # type: ignore[name-defined]
