"""Circles API schemas."""

from datetime import date, datetime
from uuid import UUID

from pydantic import BaseModel, Field, field_validator


class PingResponse(BaseModel):
    module: str
    status: str


class CircleCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    contribution_amount_minor: int = Field(gt=0)
    member_count_target: int = Field(ge=2, le=32)
    cycle_count: int = Field(ge=1, le=32)
    cadence: str = Field(default="monthly")
    start_date: date

    @field_validator("name")
    @classmethod
    def normalize_name(cls, value: str) -> str:
        normalized = " ".join(value.split())
        if not normalized:
            raise ValueError("Circle name is required.")
        return normalized

    @field_validator("cadence")
    @classmethod
    def validate_cadence(cls, value: str) -> str:
        if value != "monthly":
            raise ValueError("Only monthly cadence is supported in M2.")
        return value


class CircleMemberResponse(BaseModel):
    member_id: UUID
    role: str
    status: str
    joined_at: datetime | None


class CircleResponse(BaseModel):
    id: UUID
    name: str
    state: str
    currency: str
    contribution_amount_minor: int
    member_count_target: int
    cycle_count: int
    cadence: str
    start_date: date
    owner_member_id: UUID
    member_count: int
    agreed_count: int
    created_at: datetime
    locked_at: datetime | None
    completed_at: datetime | None


class CircleDetailResponse(CircleResponse):
    members: list[CircleMemberResponse]


class CircleListResponse(BaseModel):
    items: list[CircleResponse]


class CircleInviteRequest(BaseModel):
    email: str | None = Field(default=None, max_length=320)
    expires_in_days: int = Field(default=7, ge=1, le=60)


class CircleInviteResponse(BaseModel):
    id: UUID
    circle_id: UUID
    token: str
    email: str | None
    status: str
    expires_at: datetime


class CircleJoinRequest(BaseModel):
    token: str = Field(min_length=16, max_length=80)


class CircleAgreementRequest(BaseModel):
    contribution_amount_minor: int = Field(gt=0)
    cadence: str = "monthly"
    start_date: date
    payout_rules: dict[str, object] = Field(default_factory=dict)

    @field_validator("cadence")
    @classmethod
    def validate_cadence(cls, value: str) -> str:
        if value != "monthly":
            raise ValueError("Only monthly cadence is supported in M2.")
        return value


class CircleAgreementResponse(BaseModel):
    id: UUID
    circle_id: UUID
    member_id: UUID
    contribution_amount_minor: int
    cadence: str
    start_date: date
    payout_rules: dict[str, object]
    accepted_at: datetime


class CircleAgreementListResponse(BaseModel):
    items: list[CircleAgreementResponse]


class CircleDrawCommitRequest(BaseModel):
    commitment_hash: str = Field(min_length=64, max_length=64)


class CircleDrawRevealRequest(BaseModel):
    salt: str = Field(min_length=8, max_length=160)


class CircleDrawResponse(BaseModel):
    circle_id: UUID
    commitment_hash: str | None
    salt: str | None
    revealed_at: datetime | None
    payout_order: list[UUID]


class CircleCycleResponse(BaseModel):
    id: UUID
    position: int
    recipient_member_id: UUID
    due_date: date
    status: str


class CircleContributionResponse(BaseModel):
    id: UUID
    cycle_id: UUID
    member_id: UUID
    amount_minor: int
    status: str
    due_date: date
    payment_object_id: UUID | None


class CircleContributionListResponse(BaseModel):
    items: list[CircleContributionResponse]


class CirclePayoutResponse(BaseModel):
    id: UUID
    circle_id: UUID
    cycle_id: UUID
    recipient_member_id: UUID
    amount_minor: int
    shortfall_minor: int
    status: str
    payment_object_id: UUID | None
    journal_entry_id: UUID | None


class CircleLedgerItemResponse(BaseModel):
    posting_id: UUID
    journal_entry_id: UUID
    created_at: datetime
    account_code: str
    description: str
    amount_minor: int
    side: str


class CircleLedgerResponse(BaseModel):
    items: list[CircleLedgerItemResponse]


class CircleStatementResponse(BaseModel):
    period: str
    currency: str
    opening_balance_minor: int
    movement_minor: int
    closing_balance_minor: int
    journal_entry_ids: list[UUID]


class CircleRecordsResponse(BaseModel):
    arrears_count: int
    shortfall_count: int
    arrears_minor: int
    shortfall_minor: int
