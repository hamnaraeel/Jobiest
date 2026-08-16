from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.models.enums import ApplicationMaterialStatus, ApplicationQuestionType


class ApplicationQuestionCreate(BaseModel):
    question: str = Field(..., min_length=1)
    question_type: ApplicationQuestionType | None = None
    character_limit: int | None = Field(default=None, gt=0)
    word_limit: int | None = Field(default=None, gt=0)
    required: bool = True


class ApplicationQuestionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    job_id: int
    question: str
    question_type: ApplicationQuestionType
    character_limit: int | None
    word_limit: int | None
    required: bool
    created_at: datetime


class ApplicationAnswerStatusUpdateRequest(BaseModel):
    status: ApplicationMaterialStatus


class ApplicationAnswerRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    question_id: int
    answer: str
    word_count: int
    character_count: int
    status: ApplicationMaterialStatus
    evidence: list
    warnings: list[str]
    created_at: datetime
    updated_at: datetime


class ManualInputRequired(BaseModel):
    """Returned instead of ApplicationAnswerRead for question types the
    profile has no verified preference for (salary/authorization/
    relocation/availability) -- never guessed, never randomly generated."""

    status: str = "manual_input_required"
    question_type: ApplicationQuestionType
    reason: str


class NeedsManualEdit(BaseModel):
    """Returned when an answer still exceeds its length limit after the
    maximum shortening attempts -- never mechanically truncated."""

    status: str = "needs_manual_edit"
    reason: str
    answer_id: int


class ClaimValidationError(BaseModel):
    type: str
    text: str
    reason: str


class ClaimValidationReport(BaseModel):
    valid: bool
    errors: list[ClaimValidationError] = Field(default_factory=list)
