"""``opportunity_meeting`` — 商机相关的线下对接记录。

类型只有三种：一对一引荐、沙龙、闭门会。参与方以 JSONB 数组保存，元素结构
``{"role": "party_a|party_b|staff|guest", "company_id": uuid|null,
"staff_id": uuid|null, "name": str|null}``；``event_id`` 指向关联活动。
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, String, Text, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base
from app.enums import MeetingType, sql_values
from app.models.base import TenantMixin, TimestampMixin, UUIDPrimaryKeyMixin


class OpportunityMeeting(UUIDPrimaryKeyMixin, TenantMixin, TimestampMixin, Base):
    __tablename__ = "opportunity_meeting"

    opportunity_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("opportunity.id", ondelete="CASCADE"),
        nullable=False,
        comment="所属撮合商机",
    )
    meeting_type: Mapped[str] = mapped_column(
        String(20), nullable=False, comment="one_on_one / salon / closed_door"
    )
    meeting_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, comment="对接时间（计划或实际）"
    )
    participants: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB,
        nullable=False,
        default=list,
        server_default=text("'[]'::jsonb"),
        comment="参与方数组：[{role, company_id, staff_id, name}]",
    )
    summary: Mapped[str | None] = mapped_column(Text, nullable=True, comment="纪要摘要")
    event_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), nullable=True, comment="关联活动 id（沙龙/闭门会等）"
    )

    __table_args__ = (
        CheckConstraint(
            f"meeting_type IN ({sql_values(MeetingType)})",
            name="ck_opportunity_meeting_type",
        ),
        CheckConstraint(
            "jsonb_typeof(participants) = 'array'",
            name="ck_opportunity_meeting_participants_array",
        ),
        Index("ix_opportunity_meeting_opportunity", "opportunity_id", "meeting_at"),
    )

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"<OpportunityMeeting {self.id} type={self.meeting_type}>"
