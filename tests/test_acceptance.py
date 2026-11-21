"""Direct mapping of the four acceptance criteria published on the ticket.

Each test names the criterion it proves; the same behaviour is also covered in
depth by the dedicated modules (migration / constraints / service).
"""

from __future__ import annotations

import pytest
from sqlalchemy import create_engine, inspect
from sqlalchemy.exc import IntegrityError
from sqlalchemy.pool import NullPool

from app.services import OpportunityValidationError, create_opportunity
from tests import alembic_utils
from tests.factories import new_uuid, opportunity_values

TABLES = {"opportunity", "opportunity_meeting", "opportunity_stage_log"}


def _tables(url: str) -> set[str]:
    engine = create_engine(url, poolclass=NullPool)
    try:
        return set(inspect(engine).get_table_names())
    finally:
        engine.dispose()


def test_ac1_migration_upgrade_and_downgrade_succeed(roundtrip_database_url):
    """AC-1: 迁移 upgrade / downgrade 均成功。"""

    url = roundtrip_database_url
    alembic_utils.upgrade(url)
    assert TABLES <= _tables(url)

    alembic_utils.downgrade(url)
    assert not TABLES & _tables(url)

    alembic_utils.upgrade(url)
    assert TABLES <= _tables(url)
    alembic_utils.check(url)


def test_ac2_same_party_is_rejected(session):
    """AC-2: party_a 与 party_b 相同时保存失败（测试）。"""

    same = new_uuid()
    values = opportunity_values(party_a_company_id=same, party_b_company_id=same)

    with pytest.raises(OpportunityValidationError):
        create_opportunity(session, **values)

    from app.models import Opportunity

    with pytest.raises(IntegrityError):
        session.add(Opportunity(id=new_uuid(), **values))
        session.flush()
    session.rollback()


def test_ac3_negative_deal_cents_is_rejected(session):
    """AC-3: deal_cents 为负数时保存失败（测试）。"""

    from app.models import Opportunity

    with pytest.raises(IntegrityError):
        session.add(Opportunity(id=new_uuid(), **opportunity_values(deal_cents=-1)))
        session.flush()
    session.rollback()


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("stage", "negotiating"),
        ("stage", "won"),
        ("outcome", "lost"),
        ("outcome", "success"),
    ],
)
def test_ac4_invalid_stage_and_outcome_are_rejected(session, field, value):
    """AC-4: stage 与 outcome 写入非法值被拒绝（测试）。"""

    from app.models import Opportunity

    with pytest.raises(IntegrityError):
        session.add(Opportunity(id=new_uuid(), **opportunity_values(**{field: value})))
        session.flush()
    session.rollback()
