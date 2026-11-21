"""``opportunity`` — 撮合商机主表（与招商商机 ``deal`` 分表）。

五阶段中 ① 需求发布、② AI 匹配的对象分别是供需条目与匹配记录。商机在
② 被采纳（或对接请求被受理、员工人工引荐、活动现场发起）时创建，并直接进入
③ ``follow_up``；此后依次经 ④ ``meeting``、⑤ ``outcome``，最后进入终态
``closed``。
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    Index,
    SmallInteger,
    String,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base
from app.enums import (
    LOST_REASON_LABELS,
    LostReason,
    Origin,
    Outcome,
    Stage,
    sql_values,
)
from app.models.base import TenantMixin, TimestampMixin, UUIDPrimaryKeyMixin


class Opportunity(UUIDPrimaryKeyMixin, TenantMixin, TimestampMixin, Base):
    __tablename__ = "opportunity"

    # ---- 来源与对象引用 -------------------------------------------------
    source_item_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        nullable=True,
        comment="需求条目（supply/demand item）id；员工人工引荐时可为空",
    )
    match_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), nullable=True, comment="AI 匹配记录 id；非 ai_match 入口为空"
    )
    connect_request_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), nullable=True, comment="对接请求 id；member_initiated 入口必填"
    )
    party_a_company_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), nullable=False, comment="需求方企业 id"
    )
    party_b_company_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), nullable=False, comment="供给方企业 id"
    )
    origin: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        comment="创建入口：ai_match / member_initiated / staff_intro / event",
    )
    event_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), nullable=True, comment="活动 id；origin=event 时必填"
    )
    owner_staff_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), nullable=False, comment="负责会员经理（员工）id"
    )

    # ---- 阶段与关键时间 -------------------------------------------------
    stage: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default=Stage.FOLLOW_UP.value,
        server_default=text(f"'{Stage.FOLLOW_UP.value}'"),
        comment="follow_up / meeting / outcome / closed",
    )
    stage_entered_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    first_contacted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    party_a_confirmed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    party_b_confirmed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # ---- 结果 -----------------------------------------------------------
    outcome: Mapped[str | None] = mapped_column(
        String(15), nullable=True, comment="deal / no_deal / on_hold，仅 ⑤ 之后写入"
    )
    lost_reason: Mapped[str | None] = mapped_column(
        String(30), nullable=True, comment="未成交原因字典值，见 app.enums.LostReason"
    )
    deal_cents: Mapped[int | None] = mapped_column(
        BigInteger, nullable=True, comment="成交金额，单位：分（整数），未成交为空"
    )
    feedback_a: Mapped[int | None] = mapped_column(
        SmallInteger, nullable=True, comment="需求方反馈 1–5"
    )
    feedback_b: Mapped[int | None] = mapped_column(
        SmallInteger, nullable=True, comment="供给方反馈 1–5"
    )
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # ---- 贡献人 ---------------------------------------------------------
    contributors: Mapped[list[uuid.UUID]] = mapped_column(
        ARRAY(UUID(as_uuid=True)),
        nullable=False,
        default=list,
        server_default=text("'{}'::uuid[]"),
        comment="贡献员工数组（可多人）",
    )

    __table_args__ = (
        CheckConstraint(
            "party_a_company_id <> party_b_company_id",
            name="ck_opportunity_party_distinct",
        ),
        CheckConstraint(
            "deal_cents IS NULL OR deal_cents >= 0",
            name="ck_opportunity_deal_cents_nonneg",
        ),
        CheckConstraint(
            f"origin IN ({sql_values(Origin)})",
            name="ck_opportunity_origin",
        ),
        CheckConstraint(
            f"stage IN ({sql_values(Stage)})",
            name="ck_opportunity_stage",
        ),
        CheckConstraint(
            f"outcome IS NULL OR outcome IN ({sql_values(Outcome)})",
            name="ck_opportunity_outcome",
        ),
        CheckConstraint(
            f"lost_reason IS NULL OR lost_reason IN ({sql_values(LostReason)})",
            name="ck_opportunity_lost_reason",
        ),
        CheckConstraint(
            "feedback_a IS NULL OR feedback_a BETWEEN 1 AND 5",
            name="ck_opportunity_feedback_a_range",
        ),
        CheckConstraint(
            "feedback_b IS NULL OR feedback_b BETWEEN 1 AND 5",
            name="ck_opportunity_feedback_b_range",
        ),
        Index("ix_opportunity_org_site", "org_id", "site_id"),
        Index("ix_opportunity_party_a", "party_a_company_id"),
        Index("ix_opportunity_party_b", "party_b_company_id"),
        Index("ix_opportunity_owner_staff", "owner_staff_id"),
        Index("ix_opportunity_stage", "stage"),
        Index("ix_opportunity_created_at", "created_at"),
    )

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"<Opportunity {self.id} stage={self.stage} origin={self.origin}>"


#: 中文标签导出，便于接口层直接复用（本单不提供 HTTP 接口）。
OPPORTUNITY_LOST_REASON_LABELS = LOST_REASON_LABELS
