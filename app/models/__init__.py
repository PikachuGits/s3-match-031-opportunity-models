"""Register every delivery table on ``Base.metadata`` (import order matters)."""

from __future__ import annotations

from app.models.opportunity import Opportunity
from app.models.opportunity_meeting import OpportunityMeeting
from app.models.opportunity_stage_log import OpportunityStageLog

__all__ = ["Opportunity", "OpportunityMeeting", "OpportunityStageLog"]
