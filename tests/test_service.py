"""Service-layer behaviour: entry wiring, stage transitions, outcomes, closing."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from app.enums import LostReason, MeetingType, Origin, Outcome, Stage
from app.services import (
    OpportunityValidationError,
    add_contributor,
    advance_stage,
    close_opportunity,
    create_opportunity,
    record_meeting,
    record_outcome,
    stage_history,
)
from tests.factories import new_uuid, opportunity_values


def _create(session, origin: Origin | str = Origin.AI_MATCH, **overrides):
    origin_value = origin.value if isinstance(origin, Origin) else str(origin)
    values = opportunity_values(origin=origin_value)
    if origin_value == Origin.MEMBER_INITIATED.value:
        values.pop("match_id", None)
        values["connect_request_id"] = new_uuid()
    elif origin_value == Origin.STAFF_INTRO.value:
        values.pop("match_id", None)
    elif origin_value == Origin.EVENT.value:
        values.pop("match_id", None)
        values["event_id"] = new_uuid()
    values.update(overrides)
    return create_opportunity(session, **values)


# --------------------------------------------------------------------------- 创建


@pytest.mark.parametrize("origin", list(Origin))
def test_create_each_origin_starts_in_follow_up(session, origin):
    opportunity = _create(session, origin)

    assert opportunity.stage == Stage.FOLLOW_UP.value
    assert opportunity.origin == origin.value
    assert opportunity.stage_entered_at is not None
    assert opportunity.outcome is None
    assert opportunity.deal_cents is None
    assert opportunity.contributors == []

    history = stage_history(session, opportunity.id)
    assert len(history) == 1
    assert history[0].from_stage is None
    assert history[0].to_stage == Stage.FOLLOW_UP.value


def test_staff_intro_allows_empty_source_item(session):
    opportunity = _create(session, Origin.STAFF_INTRO)
    assert opportunity.source_item_id is None
    assert opportunity.match_id is None


@pytest.mark.parametrize(
    ("origin", "missing", "message"),
    [
        (Origin.AI_MATCH, "match_id", "match_id"),
        (Origin.MEMBER_INITIATED, "connect_request_id", "connect_request_id"),
        (Origin.EVENT, "event_id", "event_id"),
    ],
)
def test_entry_point_requires_its_link(session, origin, missing, message):
    with pytest.raises(OpportunityValidationError, match=message):
        _create(session, origin, **{missing: None})


def test_same_party_rejected_by_service(session):
    same = new_uuid()
    with pytest.raises(OpportunityValidationError, match="不能相同"):
        _create(session, party_a_company_id=same, party_b_company_id=same)


def test_unknown_origin_rejected_by_service(session):
    with pytest.raises(OpportunityValidationError, match="origin"):
        _create(session, origin="referral")


def test_owner_staff_is_required(session):
    with pytest.raises(OpportunityValidationError, match="owner_staff_id"):
        _create(session, owner_staff_id=None)


def test_contributors_are_deduplicated(session):
    staff = new_uuid()
    opportunity = _create(session, contributors=[staff, str(staff)])
    assert opportunity.contributors == [staff]


def test_invalid_uuid_is_rejected(session):
    with pytest.raises(OpportunityValidationError, match="UUID"):
        _create(session, party_a_company_id="not-a-uuid")


# --------------------------------------------------------------------------- 阶段流转


def test_advance_stage_writes_log(session):
    opportunity = _create(session)
    log = advance_stage(session, opportunity, Stage.MEETING, operator_staff_id=new_uuid())

    assert opportunity.stage == Stage.MEETING.value
    assert log.from_stage == Stage.FOLLOW_UP.value
    assert log.to_stage == Stage.MEETING.value
    assert log.operator_staff_id is not None
    assert len(stage_history(session, opportunity.id)) == 2


def test_advance_to_same_stage_rejected(session):
    opportunity = _create(session)
    with pytest.raises(OpportunityValidationError, match="已处于"):
        advance_stage(session, opportunity, Stage.FOLLOW_UP)


def test_silent_rollback_rejected(session):
    opportunity = _create(session)
    advance_stage(session, opportunity, Stage.OUTCOME)
    with pytest.raises(OpportunityValidationError, match="reason"):
        advance_stage(session, opportunity, Stage.MEETING)


def test_rollback_with_reason_allowed(session):
    opportunity = _create(session)
    advance_stage(session, opportunity, Stage.OUTCOME)
    log = advance_stage(session, opportunity, Stage.FOLLOW_UP, reason="对方需要重新评估")

    assert opportunity.stage == Stage.FOLLOW_UP.value
    assert log.from_stage == Stage.OUTCOME.value
    assert log.to_stage == Stage.FOLLOW_UP.value
    assert log.reason == "对方需要重新评估"


def test_unknown_stage_rejected(session):
    opportunity = _create(session)
    with pytest.raises(OpportunityValidationError, match="stage"):
        advance_stage(session, opportunity, "won")


def test_closing_without_outcome_rejected(session):
    opportunity = _create(session)
    with pytest.raises(OpportunityValidationError, match="outcome"):
        advance_stage(session, opportunity, Stage.CLOSED)


def test_closed_is_terminal(session):
    opportunity = _create(session)
    record_outcome(session, opportunity, outcome=Outcome.DEAL, deal_cents=100)
    close_opportunity(session, opportunity)
    with pytest.raises(OpportunityValidationError, match="终态"):
        advance_stage(session, opportunity, Stage.MEETING)


# --------------------------------------------------------------------------- 线下对接


def _participants(opportunity):
    return [
        {"role": "party_a", "company_id": str(opportunity.party_a_company_id)},
        {"role": "party_b", "company_id": str(opportunity.party_b_company_id)},
        {"role": "staff", "staff_id": str(opportunity.owner_staff_id), "name": "示例会员经理"},
    ]


@pytest.mark.parametrize("meeting_type", list(MeetingType))
def test_record_meeting_advances_to_meeting(session, meeting_type):
    opportunity = _create(session)
    meeting = record_meeting(
        session,
        opportunity,
        meeting_type=meeting_type,
        meeting_at=datetime.now(UTC) + timedelta(days=2),
        participants=_participants(opportunity),
        summary="虚构纪要：双方就供给范围达成初步一致",
    )
    assert meeting.meeting_type == meeting_type.value
    assert opportunity.stage == Stage.MEETING.value
    assert stage_history(session, opportunity.id)[-1].to_stage == Stage.MEETING.value


def test_record_meeting_can_skip_stage_change(session):
    opportunity = _create(session)
    record_meeting(
        session,
        opportunity,
        meeting_type=MeetingType.SALON,
        meeting_at=datetime.now(UTC),
        participants=_participants(opportunity),
        advance=False,
    )
    assert opportunity.stage == Stage.FOLLOW_UP.value


def test_meeting_requires_participants(session):
    opportunity = _create(session)
    with pytest.raises(OpportunityValidationError, match="participants"):
        record_meeting(
            session,
            opportunity,
            meeting_type=MeetingType.ONE_ON_ONE,
            meeting_at=datetime.now(UTC),
            participants=[],
        )


def test_meeting_rejects_unknown_participant_role(session):
    opportunity = _create(session)
    with pytest.raises(OpportunityValidationError, match="role"):
        record_meeting(
            session,
            opportunity,
            meeting_type=MeetingType.ONE_ON_ONE,
            meeting_at=datetime.now(UTC),
            participants=[{"role": "boss"}],
        )


def test_meeting_requires_timezone_aware_datetime(session):
    opportunity = _create(session)
    with pytest.raises(OpportunityValidationError, match="时区"):
        record_meeting(
            session,
            opportunity,
            meeting_type=MeetingType.ONE_ON_ONE,
            meeting_at=datetime(2026, 12, 1, 10, 0),
            participants=_participants(opportunity),
        )


def test_meeting_rejects_unknown_type(session):
    opportunity = _create(session)
    with pytest.raises(OpportunityValidationError, match="meeting_type"):
        record_meeting(
            session,
            opportunity,
            meeting_type="dinner",
            meeting_at=datetime.now(UTC),
            participants=_participants(opportunity),
        )


# --------------------------------------------------------------------------- 结果


def test_deal_requires_amount(session):
    opportunity = _create(session)
    with pytest.raises(OpportunityValidationError, match="deal_cents"):
        record_outcome(session, opportunity, outcome=Outcome.DEAL)


@pytest.mark.parametrize("amount", [0, 12500])
def test_deal_accepts_non_negative_amount(session, amount):
    opportunity = _create(session)
    record_outcome(session, opportunity, outcome=Outcome.DEAL, deal_cents=amount)
    assert opportunity.stage == Stage.OUTCOME.value
    assert opportunity.outcome == Outcome.DEAL.value
    assert opportunity.deal_cents == amount


def test_deal_rejects_negative_amount(session):
    opportunity = _create(session)
    with pytest.raises(OpportunityValidationError, match="负数"):
        record_outcome(session, opportunity, outcome=Outcome.DEAL, deal_cents=-1)


def test_no_deal_requires_lost_reason(session):
    opportunity = _create(session)
    with pytest.raises(OpportunityValidationError, match="lost_reason"):
        record_outcome(session, opportunity, outcome=Outcome.NO_DEAL)


def test_no_deal_rejects_amount(session):
    opportunity = _create(session)
    with pytest.raises(OpportunityValidationError, match="deal_cents"):
        record_outcome(
            session,
            opportunity,
            outcome=Outcome.NO_DEAL,
            lost_reason=LostReason.BUDGET_MISMATCH,
            deal_cents=100,
        )


def test_no_deal_records_reason(session):
    opportunity = _create(session)
    record_outcome(
        session,
        opportunity,
        outcome=Outcome.NO_DEAL,
        lost_reason=LostReason.REGION_MISMATCH,
        feedback_a=2,
        feedback_b=3,
    )
    assert opportunity.outcome == Outcome.NO_DEAL.value
    assert opportunity.lost_reason == LostReason.REGION_MISMATCH.value
    assert opportunity.feedback_a == 2


def test_on_hold_is_allowed_without_amount(session):
    opportunity = _create(session)
    record_outcome(session, opportunity, outcome=Outcome.ON_HOLD)
    assert opportunity.outcome == Outcome.ON_HOLD.value


@pytest.mark.parametrize("value", [0, 6, -1])
def test_feedback_out_of_range_rejected_by_service(session, value):
    opportunity = _create(session)
    with pytest.raises(OpportunityValidationError, match="1–5"):
        record_outcome(
            session,
            opportunity,
            outcome=Outcome.ON_HOLD,
            feedback_a=value,
        )


def test_unknown_lost_reason_rejected_by_service(session):
    opportunity = _create(session)
    with pytest.raises(OpportunityValidationError, match="lost_reason"):
        record_outcome(
            session,
            opportunity,
            outcome=Outcome.NO_DEAL,
            lost_reason="price",
        )


def test_unknown_outcome_rejected_by_service(session):
    opportunity = _create(session)
    with pytest.raises(OpportunityValidationError, match="outcome"):
        record_outcome(session, opportunity, outcome="won")


# --------------------------------------------------------------------------- 关闭


def test_close_requires_outcome(session):
    opportunity = _create(session)
    with pytest.raises(OpportunityValidationError, match="outcome"):
        close_opportunity(session, opportunity)


def test_close_rejects_on_hold(session):
    opportunity = _create(session)
    record_outcome(session, opportunity, outcome=Outcome.ON_HOLD)
    with pytest.raises(OpportunityValidationError, match="暂缓"):
        close_opportunity(session, opportunity)


def test_close_sets_closed_at_and_logs(session):
    opportunity = _create(session)
    record_outcome(session, opportunity, outcome=Outcome.DEAL, deal_cents=8800)
    log = close_opportunity(session, opportunity, reason="款已到账，归档")

    assert opportunity.stage == Stage.CLOSED.value
    assert opportunity.closed_at is not None
    assert log.to_stage == Stage.CLOSED.value
    assert log.reason == "款已到账，归档"


def test_double_close_rejected(session):
    opportunity = _create(session)
    record_outcome(session, opportunity, outcome=Outcome.DEAL, deal_cents=100)
    close_opportunity(session, opportunity)
    with pytest.raises(OpportunityValidationError, match="已 closed"):
        close_opportunity(session, opportunity)


def test_outcome_after_close_rejected(session):
    opportunity = _create(session)
    record_outcome(session, opportunity, outcome=Outcome.DEAL, deal_cents=100)
    close_opportunity(session, opportunity)
    with pytest.raises(OpportunityValidationError, match="终态"):
        record_outcome(session, opportunity, outcome=Outcome.DEAL, deal_cents=200)


# --------------------------------------------------------------------------- 其他


def test_add_contributor_is_idempotent(session):
    opportunity = _create(session)
    staff = new_uuid()
    first = add_contributor(session, opportunity, staff)
    second = add_contributor(session, opportunity, staff)
    assert first == second == [staff]


def test_stage_history_is_ordered(session):
    opportunity = _create(session)
    advance_stage(session, opportunity, Stage.MEETING)
    record_outcome(session, opportunity, outcome=Outcome.DEAL, deal_cents=100)
    close_opportunity(session, opportunity)

    history = stage_history(session, opportunity.id)
    assert [(row.from_stage, row.to_stage) for row in history] == [
        (None, "follow_up"),
        ("follow_up", "meeting"),
        ("meeting", "outcome"),
        ("outcome", "closed"),
    ]
    timestamps = [row.occurred_at for row in history]
    assert timestamps == sorted(timestamps)
