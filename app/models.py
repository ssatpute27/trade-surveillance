from typing import Literal
from pydantic import BaseModel, ConfigDict, Field
from uuid import UUID


class StrictModel(BaseModel):
    model_config = ConfigDict(extra='forbid')


class Citation(StrictModel):
    evidence_id: str
    quote: str = Field(min_length=1)


class Claim(StrictModel):
    text: str
    citations: list[Citation] = Field(min_length=1)


class Report(StrictModel):
    assessment: Literal['concerning', 'plausibly_benign', 'inconclusive']
    recommendation: Literal['escalate', 'standard_review', 'request_more_evidence']
    summary: Claim
    observations: list[Claim] = Field(min_length=1)
    alternative_explanations: list[Claim] = Field(min_length=1)
    gaps: list[Claim]
    reviewer_questions: list[str] = Field(min_length=1)


class ToolArgs(StrictModel):
    reason: str = Field(min_length=1, max_length=300)
    query: str = Field(max_length=500)


class InitialAssessment(StrictModel):
    reason: str = Field(min_length=1,max_length=300)
    assessment: Literal['concerning','plausibly_benign','inconclusive']
    summary: Claim


class Promotion(StrictModel):
    reason: str = Field(min_length=1,max_length=300)
    evidence_ids: list[str] = Field(min_length=1)


class GroundingVerdict(StrictModel):
    supported: bool
    issues: list[str]
    flagged_claims: list[str]


class SubmittedEvidence(StrictModel):
    title: str = Field(min_length=3,max_length=160)
    reference: str = Field(min_length=3,max_length=200)
    content: str = Field(min_length=20,max_length=12000)


class Action(StrictModel):
    action: Literal['escalate', 'request_more_evidence', 'mark_reviewed']
    note: str = Field(min_length=3, max_length=3000)
    evidence: SubmittedEvidence | None = None
    demo_verification: bool = False


class AnalystReviewRequest(Action):
    run_id: UUID


class ManagerAction(StrictModel):
    action: Literal['return_for_evidence','assign_investigation','approve_closure','refer']
    note: str = Field(min_length=5,max_length=3000)
    owner: str = Field(default='',max_length=160)
    destination: Literal['','Compliance investigations','Legal team'] = ''
    closure_reason: Literal['','explained_activity','insufficient_basis_after_review','duplicate_case','resolved_control_issue'] = ''
    run_id: UUID
    version: int = Field(ge=1)
    request_id: UUID


class Intake(StrictModel):
    alert_id: Literal['TS-1042', 'TS-1043', 'TS-1044']
    mode: Literal['live', 'replay'] = 'live'
