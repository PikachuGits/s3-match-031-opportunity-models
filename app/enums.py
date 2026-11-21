"""Domain vocabularies for the matching opportunity module.

All enumerations are the single source of truth: the models render them into
PostgreSQL ``CHECK`` constraints and the service layer validates with the same
members, so a value accepted by Python can never be rejected by the database
(and vice versa).
"""

from __future__ import annotations

from enum import StrEnum


class Origin(StrEnum):
    """How the opportunity came into existence (② 之后创建商机的四种入口)."""

    AI_MATCH = "ai_match"
    MEMBER_INITIATED = "member_initiated"
    STAFF_INTRO = "staff_intro"
    EVENT = "event"


class Stage(StrEnum):
    """Five-stage flow, ③–⑤ plus the terminal state."""

    FOLLOW_UP = "follow_up"
    MEETING = "meeting"
    OUTCOME = "outcome"
    CLOSED = "closed"


class Outcome(StrEnum):
    DEAL = "deal"
    NO_DEAL = "no_deal"
    ON_HOLD = "on_hold"


class MeetingType(StrEnum):
    ONE_ON_ONE = "one_on_one"
    SALON = "salon"
    CLOSED_DOOR = "closed_door"


class LostReason(StrEnum):
    """``lost_reason`` dictionary values (中文标签见 ``LOST_REASON_LABELS``)."""

    DEMAND_WITHDRAWN = "demand_withdrawn"
    BUDGET_MISMATCH = "budget_mismatch"
    REGION_MISMATCH = "region_mismatch"
    TIMING_CONFLICT = "timing_conflict"
    NO_INTENT = "no_intent"
    QUALIFICATION_MISMATCH = "qualification_mismatch"
    OTHER = "other"


ORIGIN_LABELS: dict[Origin, str] = {
    Origin.AI_MATCH: "AI 匹配被采纳",
    Origin.MEMBER_INITIATED: "会员主动发起对接请求",
    Origin.STAFF_INTRO: "员工人工引荐",
    Origin.EVENT: "活动现场发起",
}

STAGE_LABELS: dict[Stage, str] = {
    Stage.FOLLOW_UP: "③ 员工跟进",
    Stage.MEETING: "④ 线下对接",
    Stage.OUTCOME: "⑤ 成交记录",
    Stage.CLOSED: "已关闭",
}

OUTCOME_LABELS: dict[Outcome, str] = {
    Outcome.DEAL: "成交",
    Outcome.NO_DEAL: "未成交",
    Outcome.ON_HOLD: "暂缓",
}

MEETING_TYPE_LABELS: dict[MeetingType, str] = {
    MeetingType.ONE_ON_ONE: "一对一引荐",
    MeetingType.SALON: "沙龙",
    MeetingType.CLOSED_DOOR: "闭门会",
}

LOST_REASON_LABELS: dict[LostReason, str] = {
    LostReason.DEMAND_WITHDRAWN: "需求方撤回需求",
    LostReason.BUDGET_MISMATCH: "预算不匹配",
    LostReason.REGION_MISMATCH: "服务地域不匹配",
    LostReason.TIMING_CONFLICT: "时间冲突",
    LostReason.NO_INTENT: "双方无成交意愿",
    LostReason.QUALIFICATION_MISMATCH: "资质或能力不匹配",
    LostReason.OTHER: "其他",
}

#: Position of each stage in the linear flow, used to reject silent rollbacks.
STAGE_ORDER: dict[Stage, int] = {
    Stage.FOLLOW_UP: 1,
    Stage.MEETING: 2,
    Stage.OUTCOME: 3,
    Stage.CLOSED: 4,
}


def sql_values(enum_cls: type[StrEnum]) -> str:
    """Render members as a SQL ``IN`` list, keeping DDL and Python in sync."""

    return ", ".join(f"'{member.value}'" for member in enum_cls)
