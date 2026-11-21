"""S3-MATCH-031: 撮合商机 opportunity / 线下对接 / 阶段留痕三张表

Revision ID: 0001_opportunity
Revises:
Create Date: 2026-11-21
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0001_opportunity"
down_revision = None
branch_labels = None
depends_on = None

UUID = postgresql.UUID(as_uuid=True)
ARRAY_UUID = postgresql.ARRAY(postgresql.UUID(as_uuid=True))

# Verbatim copies of app.enums — asserted equal by tests/test_enums.py so a
# vocabulary change cannot land without updating the migration.
ORIGIN_IN = "'ai_match', 'member_initiated', 'staff_intro', 'event'"
STAGE_IN = "'follow_up', 'meeting', 'outcome', 'closed'"
OUTCOME_IN = "'deal', 'no_deal', 'on_hold'"
MEETING_TYPE_IN = "'one_on_one', 'salon', 'closed_door'"
LOST_REASON_IN = (
    "'demand_withdrawn', 'budget_mismatch', 'region_mismatch', 'timing_conflict', "
    "'no_intent', 'qualification_mismatch', 'other'"
)


def upgrade() -> None:
    # ---------------------------------------------------------------- opportunity
    op.create_table(
        "opportunity",
        sa.Column("id", UUID, server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("org_id", UUID, nullable=False),
        sa.Column("site_id", UUID, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("created_by", UUID, nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("source_item_id", UUID, nullable=True, comment="需求条目（supply/demand item）id；员工人工引荐时可为空"),
        sa.Column("match_id", UUID, nullable=True, comment="AI 匹配记录 id；非 ai_match 入口为空"),
        sa.Column("connect_request_id", UUID, nullable=True, comment="对接请求 id；member_initiated 入口必填"),
        sa.Column("party_a_company_id", UUID, nullable=False, comment="需求方企业 id"),
        sa.Column("party_b_company_id", UUID, nullable=False, comment="供给方企业 id"),
        sa.Column("origin", sa.String(length=20), nullable=False, comment="创建入口：ai_match / member_initiated / staff_intro / event"),
        sa.Column("event_id", UUID, nullable=True, comment="活动 id；origin=event 时必填"),
        sa.Column("owner_staff_id", UUID, nullable=False, comment="负责会员经理（员工）id"),
        sa.Column("stage", sa.String(length=20), server_default=sa.text("'follow_up'"), nullable=False, comment="follow_up / meeting / outcome / closed"),
        sa.Column("stage_entered_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("first_contacted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("party_a_confirmed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("party_b_confirmed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("outcome", sa.String(length=15), nullable=True, comment="deal / no_deal / on_hold，仅 ⑤ 之后写入"),
        sa.Column("lost_reason", sa.String(length=30), nullable=True, comment="未成交原因字典值，见 app.enums.LostReason"),
        sa.Column("deal_cents", sa.BigInteger(), nullable=True, comment="成交金额，单位：分（整数），未成交为空"),
        sa.Column("feedback_a", sa.SmallInteger(), nullable=True, comment="需求方反馈 1–5"),
        sa.Column("feedback_b", sa.SmallInteger(), nullable=True, comment="供给方反馈 1–5"),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("contributors", ARRAY_UUID, server_default=sa.text("'{}'::uuid[]"), nullable=False, comment="贡献员工数组（可多人）"),
        sa.PrimaryKeyConstraint("id", name="pk_opportunity"),
        sa.CheckConstraint("party_a_company_id <> party_b_company_id", name="ck_opportunity_party_distinct"),
        sa.CheckConstraint("deal_cents IS NULL OR deal_cents >= 0", name="ck_opportunity_deal_cents_nonneg"),
        sa.CheckConstraint(f"origin IN ({ORIGIN_IN})", name="ck_opportunity_origin"),
        sa.CheckConstraint(f"stage IN ({STAGE_IN})", name="ck_opportunity_stage"),
        sa.CheckConstraint(f"outcome IS NULL OR outcome IN ({OUTCOME_IN})", name="ck_opportunity_outcome"),
        sa.CheckConstraint(f"lost_reason IS NULL OR lost_reason IN ({LOST_REASON_IN})", name="ck_opportunity_lost_reason"),
        sa.CheckConstraint("feedback_a IS NULL OR feedback_a BETWEEN 1 AND 5", name="ck_opportunity_feedback_a_range"),
        sa.CheckConstraint("feedback_b IS NULL OR feedback_b BETWEEN 1 AND 5", name="ck_opportunity_feedback_b_range"),
    )
    op.create_index("ix_opportunity_org_site", "opportunity", ["org_id", "site_id"])
    op.create_index("ix_opportunity_party_a", "opportunity", ["party_a_company_id"])
    op.create_index("ix_opportunity_party_b", "opportunity", ["party_b_company_id"])
    op.create_index("ix_opportunity_owner_staff", "opportunity", ["owner_staff_id"])
    op.create_index("ix_opportunity_stage", "opportunity", ["stage"])
    op.create_index("ix_opportunity_created_at", "opportunity", ["created_at"])

    # -------------------------------------------------------- opportunity_meeting
    op.create_table(
        "opportunity_meeting",
        sa.Column("id", UUID, server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("org_id", UUID, nullable=False),
        sa.Column("site_id", UUID, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("created_by", UUID, nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("opportunity_id", UUID, nullable=False, comment="所属撮合商机"),
        sa.Column("meeting_type", sa.String(length=20), nullable=False, comment="one_on_one / salon / closed_door"),
        sa.Column("meeting_at", sa.DateTime(timezone=True), nullable=False, comment="对接时间（计划或实际）"),
        sa.Column("participants", postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'[]'::jsonb"), nullable=False, comment="参与方数组：[{role, company_id, staff_id, name}]"),
        sa.Column("summary", sa.Text(), nullable=True, comment="纪要摘要"),
        sa.Column("event_id", UUID, nullable=True, comment="关联活动 id（沙龙/闭门会等）"),
        sa.PrimaryKeyConstraint("id", name="pk_opportunity_meeting"),
        sa.ForeignKeyConstraint(
            ["opportunity_id"], ["opportunity.id"],
            name="fk_opportunity_meeting_opportunity", ondelete="CASCADE",
        ),
        sa.CheckConstraint(f"meeting_type IN ({MEETING_TYPE_IN})", name="ck_opportunity_meeting_type"),
        sa.CheckConstraint("jsonb_typeof(participants) = 'array'", name="ck_opportunity_meeting_participants_array"),
    )
    op.create_index(
        "ix_opportunity_meeting_opportunity", "opportunity_meeting", ["opportunity_id", "meeting_at"]
    )

    # ---------------------------------------------------- opportunity_stage_log
    op.create_table(
        "opportunity_stage_log",
        sa.Column("id", UUID, server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("org_id", UUID, nullable=False),
        sa.Column("site_id", UUID, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("created_by", UUID, nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("opportunity_id", UUID, nullable=False),
        sa.Column("from_stage", sa.String(length=20), nullable=True, comment="来源阶段；创建时的首条为空"),
        sa.Column("to_stage", sa.String(length=20), nullable=False, comment="目标阶段"),
        sa.Column("operator_staff_id", UUID, nullable=True, comment="操作人；系统自动推进时为空"),
        sa.Column("reason", sa.Text(), nullable=True, comment="变更原因"),
        sa.Column("occurred_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_opportunity_stage_log"),
        sa.ForeignKeyConstraint(
            ["opportunity_id"], ["opportunity.id"],
            name="fk_opportunity_stage_log_opportunity", ondelete="CASCADE",
        ),
        sa.CheckConstraint(f"from_stage IS NULL OR from_stage IN ({STAGE_IN})", name="ck_opportunity_stage_log_from"),
        sa.CheckConstraint(f"to_stage IN ({STAGE_IN})", name="ck_opportunity_stage_log_to"),
    )
    op.create_index(
        "ix_opportunity_stage_log_opportunity", "opportunity_stage_log", ["opportunity_id", "occurred_at"]
    )


def downgrade() -> None:
    op.drop_index("ix_opportunity_stage_log_opportunity", table_name="opportunity_stage_log")
    op.drop_table("opportunity_stage_log")

    op.drop_index("ix_opportunity_meeting_opportunity", table_name="opportunity_meeting")
    op.drop_table("opportunity_meeting")

    op.drop_index("ix_opportunity_created_at", table_name="opportunity")
    op.drop_index("ix_opportunity_stage", table_name="opportunity")
    op.drop_index("ix_opportunity_owner_staff", table_name="opportunity")
    op.drop_index("ix_opportunity_party_b", table_name="opportunity")
    op.drop_index("ix_opportunity_party_a", table_name="opportunity")
    op.drop_index("ix_opportunity_org_site", table_name="opportunity")
    op.drop_table("opportunity")
