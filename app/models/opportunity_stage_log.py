"""``opportunity_stage_log`` — 阶段流转留痕。

每次阶段变更写一条，``from_stage`` 为空表示“创建即进入 ③”。日志只追加，
不随商机软删除而清理，由外键 ``ON DELETE CASCADE`` 跟随物理删除。
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base
from app.enums import Stage, sql_values
from app.models.base import TenantMixin, TimestampMixin, UUIDPrimaryKeyMixin


class OpportunityStageLog(UUIDPrimaryKeyMixin, TenantMixin, TimestampMixin, Base):
    __tablename__ = "opportunity_stage_log"

    opportunity_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("opportunity.id", ondelete="CASCADE"),
        nullable=False,
    )
    from_stage: Mapped[str | None] = mapped_column(
        String(20), nullable=True, comment="来源阶段；创建时的首条为空"
    )
    to_stage: Mapped[str] = mapped_column(String(20), nullable=False, comment="目标阶段")
    operator_staff_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), nullable=True, comment="操作人；系统自动推进时为空"
    )
    reason: Mapped[str | None] = mapped_column(Text, nullable=True, comment="变更原因")
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    __table_args__ = (
        CheckConstraint(
            f"from_stage IS NULL OR from_stage IN ({sql_values(Stage)})",
            name="ck_opportunity_stage_log_from",
        ),
        CheckConstraint(
            f"to_stage IN ({sql_values(Stage)})",
            name="ck_opportunity_stage_log_to",
        ),
        Index("ix_opportunity_stage_log_opportunity", "opportunity_id", "occurred_at"),
    )

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"<OpportunityStageLog {self.from_stage}->{self.to_stage}>"
