"""Domain services for the matching opportunity module.

The service layer is the only sanctioned write path: it validates the values
that the database cannot express as a column constraint (entry-point wiring,
stage transitions, outcome completeness) and writes one ``stage_log`` row for
every transition.  HTTP endpoints are out of scope for this ticket; callers are
expected to inject a ``Session`` from their own API layer.

All UUIDs, companies, staff and events used below are fictional test fixtures.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterable, Sequence
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.enums import (
    STAGE_ORDER,
    LostReason,
    MeetingType,
    Origin,
    Outcome,
    Stage,
)
from app.models import Opportunity, OpportunityMeeting, OpportunityStageLog

PARTICIPANT_ROLES = ("party_a", "party_b", "staff", "guest")


class OpportunityValidationError(ValueError):
    """Raised when a write violates a domain rule beyond the DDL constraints."""


def _now() -> datetime:
    return datetime.now(UTC)


def _as_uuid(value: Any, field: str) -> uuid.UUID:
    if isinstance(value, uuid.UUID):
        return value
    try:
        return uuid.UUID(str(value))
    except (TypeError, ValueError) as exc:
        raise OpportunityValidationError(f"{field} 不是合法的 UUID：{value!r}") from exc


def _enum(value: Any, enum_cls: type, field: str):
    try:
        return enum_cls(value)
    except ValueError as exc:
        allowed = ", ".join(member.value for member in enum_cls)
        raise OpportunityValidationError(f"{field} 取值非法：{value!r}，允许值：{allowed}") from exc


def _dedupe(values: Iterable[uuid.UUID]) -> list[uuid.UUID]:
    seen: dict[uuid.UUID, None] = {}
    for value in values:
        seen.setdefault(value, None)
    return list(seen)


# ---------------------------------------------------------------------------
# 创建
# ---------------------------------------------------------------------------


def create_opportunity(
    session: Session,
    *,
    org_id: uuid.UUID | str,
    site_id: uuid.UUID | str,
    party_a_company_id: uuid.UUID | str,
    party_b_company_id: uuid.UUID | str,
    origin: Origin | str,
    owner_staff_id: uuid.UUID | str,
    created_by: uuid.UUID | str | None = None,
    source_item_id: uuid.UUID | str | None = None,
    match_id: uuid.UUID | str | None = None,
    connect_request_id: uuid.UUID | str | None = None,
    event_id: uuid.UUID | str | None = None,
    contributors: Sequence[uuid.UUID | str] | None = None,
) -> Opportunity:
    """Create an opportunity in stage ③ ``follow_up`` and log the entry.

    Entry wiring enforced here (the columns stay nullable because each entry
    needs a different subset):

    * ``ai_match``       → ``match_id`` required
    * ``member_initiated`` → ``connect_request_id`` required
    * ``staff_intro``    → ``source_item_id`` optional (员工可无需求条目引荐)
    * ``event``          → ``event_id`` required
    """

    origin_enum = _enum(origin, Origin, "origin")
    party_a = _as_uuid(party_a_company_id, "party_a_company_id")
    party_b = _as_uuid(party_b_company_id, "party_b_company_id")

    if party_a == party_b:
        raise OpportunityValidationError("party_a_company_id 与 party_b_company_id 不能相同")

    links = {
        "match_id": _as_uuid(match_id, "match_id") if match_id else None,
        "connect_request_id": _as_uuid(connect_request_id, "connect_request_id")
        if connect_request_id
        else None,
        "source_item_id": _as_uuid(source_item_id, "source_item_id") if source_item_id else None,
        "event_id": _as_uuid(event_id, "event_id") if event_id else None,
    }

    required_link = {
        Origin.AI_MATCH: ("match_id", "AI 匹配入口必须提供 match_id"),
        Origin.MEMBER_INITIATED: ("connect_request_id", "会员发起入口必须提供 connect_request_id"),
        Origin.EVENT: ("event_id", "活动入口必须提供 event_id"),
    }.get(origin_enum)
    if required_link and links[required_link[0]] is None:
        raise OpportunityValidationError(required_link[1])

    opportunity = Opportunity(
        id=uuid.uuid4(),
        org_id=_as_uuid(org_id, "org_id"),
        site_id=_as_uuid(site_id, "site_id"),
        party_a_company_id=party_a,
        party_b_company_id=party_b,
        origin=origin_enum.value,
        owner_staff_id=_as_uuid(owner_staff_id, "owner_staff_id"),
        created_by=_as_uuid(created_by, "created_by") if created_by else None,
        contributors=_dedupe(_as_uuid(item, "contributors[]") for item in (contributors or [])),
        stage=Stage.FOLLOW_UP.value,
        stage_entered_at=_now(),
        **links,
    )
    session.add(opportunity)

    session.add(
        OpportunityStageLog(
            id=uuid.uuid4(),
            org_id=opportunity.org_id,
            site_id=opportunity.site_id,
            opportunity_id=opportunity.id,
            from_stage=None,
            to_stage=Stage.FOLLOW_UP.value,
            operator_staff_id=opportunity.created_by or opportunity.owner_staff_id,
            reason=f"商机创建（{origin_enum.value}），进入 ③ 员工跟进",
            occurred_at=_now(),
        )
    )
    session.flush()
    return opportunity


# ---------------------------------------------------------------------------
# 阶段流转
# ---------------------------------------------------------------------------


def advance_stage(
    session: Session,
    opportunity: Opportunity,
    to_stage: Stage | str,
    *,
    operator_staff_id: uuid.UUID | str | None = None,
    reason: str | None = None,
) -> OpportunityStageLog:
    """Move the opportunity to another stage and append a log row.

    Rules:

    * the same stage twice is rejected;
    * a forward move needs no reason, a backward move requires one (silent
      rollbacks hide the fact that a deal slipped);
    * ``closed`` is terminal — nothing can leave it.
    """

    target = _enum(to_stage, Stage, "stage")

    if opportunity.stage == Stage.CLOSED.value:
        raise OpportunityValidationError("商机已 closed，终态不可再变更")
    if target.value == opportunity.stage:
        raise OpportunityValidationError(f"商机已处于 {target.value} 阶段")
    if target is Stage.CLOSED and opportunity.outcome is None:
        raise OpportunityValidationError("进入 closed 前必须先写入 outcome")

    from_stage = Stage(opportunity.stage)
    if STAGE_ORDER[target] < STAGE_ORDER[from_stage] and not (reason and reason.strip()):
        raise OpportunityValidationError(
            f"从 {from_stage.value} 回退到 {target.value} 必须填写 reason"
        )

    now = _now()
    log = OpportunityStageLog(
        id=uuid.uuid4(),
        org_id=opportunity.org_id,
        site_id=opportunity.site_id,
        opportunity_id=opportunity.id,
        from_stage=from_stage.value,
        to_stage=target.value,
        operator_staff_id=_as_uuid(operator_staff_id, "operator_staff_id")
        if operator_staff_id
        else None,
        reason=reason,
        occurred_at=now,
    )
    opportunity.stage = target.value
    opportunity.stage_entered_at = now
    if target is Stage.CLOSED:
        opportunity.closed_at = now

    session.add(log)
    session.flush()
    return log


# ---------------------------------------------------------------------------
# 线下对接
# ---------------------------------------------------------------------------


def _validate_participants(participants: Sequence[dict[str, Any]]) -> list[dict[str, Any]]:
    if not participants:
        raise OpportunityValidationError("participants 不能为空")
    normalized: list[dict[str, Any]] = []
    for index, participant in enumerate(participants):
        if not isinstance(participant, dict):
            raise OpportunityValidationError(f"participants[{index}] 必须是对象")
        role = participant.get("role")
        if role not in PARTICIPANT_ROLES:
            allowed = ", ".join(PARTICIPANT_ROLES)
            raise OpportunityValidationError(
                f"participants[{index}].role 取值非法：{role!r}，允许值：{allowed}"
            )
        normalized.append(
            {
                "role": role,
                "company_id": str(participant["company_id"])
                if participant.get("company_id")
                else None,
                "staff_id": str(participant["staff_id"]) if participant.get("staff_id") else None,
                "name": participant.get("name"),
            }
        )
    return normalized


def record_meeting(
    session: Session,
    opportunity: Opportunity,
    *,
    meeting_type: MeetingType | str,
    meeting_at: datetime,
    participants: Sequence[dict[str, Any]],
    summary: str | None = None,
    event_id: uuid.UUID | str | None = None,
    created_by: uuid.UUID | str | None = None,
    advance: bool = True,
) -> OpportunityMeeting:
    """Append a ④ 线下对接 record; by default also move the stage to ``meeting``."""

    type_enum = _enum(meeting_type, MeetingType, "meeting_type")
    if meeting_at.tzinfo is None:
        raise OpportunityValidationError("meeting_at 必须带时区（timestamptz）")

    meeting = OpportunityMeeting(
        id=uuid.uuid4(),
        org_id=opportunity.org_id,
        site_id=opportunity.site_id,
        opportunity_id=opportunity.id,
        meeting_type=type_enum.value,
        meeting_at=meeting_at,
        participants=_validate_participants(participants),
        summary=summary,
        event_id=_as_uuid(event_id, "event_id") if event_id else None,
        created_by=_as_uuid(created_by, "created_by") if created_by else None,
    )
    session.add(meeting)

    if advance and opportunity.stage == Stage.FOLLOW_UP.value:
        advance_stage(
            session,
            opportunity,
            Stage.MEETING,
            operator_staff_id=created_by,
            reason=f"记录{type_enum.value}对接，进入 ④ 线下对接",
        )

    session.flush()
    return meeting


# ---------------------------------------------------------------------------
# 结果与关闭
# ---------------------------------------------------------------------------


def record_outcome(
    session: Session,
    opportunity: Opportunity,
    *,
    outcome: Outcome | str,
    operator_staff_id: uuid.UUID | str | None = None,
    deal_cents: int | None = None,
    lost_reason: LostReason | str | None = None,
    feedback_a: int | None = None,
    feedback_b: int | None = None,
    reason: str | None = None,
) -> Opportunity:
    """Write the ⑤ result. Moving to ``outcome`` stage is logged automatically."""

    outcome_enum = _enum(outcome, Outcome, "outcome")
    if opportunity.stage == Stage.CLOSED.value:
        raise OpportunityValidationError("商机已 closed，终态不可再变更")

    if deal_cents is not None:
        if isinstance(deal_cents, bool) or not isinstance(deal_cents, int):
            raise OpportunityValidationError("deal_cents 必须是整数（单位：分）")
        if deal_cents < 0:
            raise OpportunityValidationError("deal_cents 不能为负数")

    if outcome_enum is Outcome.DEAL:
        if deal_cents is None:
            raise OpportunityValidationError("outcome=deal 时必须填写 deal_cents")
    elif outcome_enum is Outcome.NO_DEAL:
        if lost_reason is None:
            raise OpportunityValidationError("outcome=no_deal 时必须填写 lost_reason")
        if deal_cents is not None:
            raise OpportunityValidationError("outcome=no_deal 时 deal_cents 必须为空")
    elif outcome_enum is Outcome.ON_HOLD and deal_cents is not None:
        raise OpportunityValidationError("outcome=on_hold 时 deal_cents 必须为空")

    for field, value in (("feedback_a", feedback_a), ("feedback_b", feedback_b)):
        if value is not None:
            if isinstance(value, bool) or not isinstance(value, int):
                raise OpportunityValidationError(f"{field} 必须是 1–5 的整数")
            if not 1 <= value <= 5:
                raise OpportunityValidationError(f"{field} 必须在 1–5 之间")

    lost_reason_enum = _enum(lost_reason, LostReason, "lost_reason") if lost_reason else None

    if opportunity.stage != Stage.OUTCOME.value:
        advance_stage(
            session,
            opportunity,
            Stage.OUTCOME,
            operator_staff_id=operator_staff_id,
            reason=reason or f"写入 ⑤ 成交记录：{outcome_enum.value}",
        )

    opportunity.outcome = outcome_enum.value
    opportunity.lost_reason = lost_reason_enum.value if lost_reason_enum else None
    opportunity.deal_cents = deal_cents
    opportunity.feedback_a = feedback_a
    opportunity.feedback_b = feedback_b

    session.flush()
    return opportunity


def close_opportunity(
    session: Session,
    opportunity: Opportunity,
    *,
    operator_staff_id: uuid.UUID | str | None = None,
    reason: str | None = None,
) -> OpportunityStageLog:
    """Close a concluded opportunity (``deal`` or ``no_deal`` only)."""

    if opportunity.stage == Stage.CLOSED.value:
        raise OpportunityValidationError("商机已 closed")
    if opportunity.outcome is None:
        raise OpportunityValidationError("关闭前必须先写入 outcome")
    if opportunity.outcome == Outcome.ON_HOLD.value:
        raise OpportunityValidationError("outcome=on_hold 的商机处于暂缓，不能直接关闭")

    return advance_stage(
        session,
        opportunity,
        Stage.CLOSED,
        operator_staff_id=operator_staff_id,
        reason=reason,
    )


# ---------------------------------------------------------------------------
# 读取辅助
# ---------------------------------------------------------------------------


def add_contributor(
    session: Session,
    opportunity: Opportunity,
    staff_id: uuid.UUID | str,
) -> list[uuid.UUID]:
    """Append a contributing staff member; duplicates are ignored."""

    member = _as_uuid(staff_id, "contributors[]")
    current = list(opportunity.contributors or [])
    if member not in current:
        current.append(member)
        opportunity.contributors = current
        session.flush()
    return current


def stage_history(session: Session, opportunity_id: uuid.UUID) -> list[OpportunityStageLog]:
    return list(
        session.scalars(
            select(OpportunityStageLog)
            .where(OpportunityStageLog.opportunity_id == opportunity_id)
            .order_by(OpportunityStageLog.occurred_at, OpportunityStageLog.created_at)
        )
    )
