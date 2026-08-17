"""Structured Ollama output schemas for Step 7's interview preparation."""

from pydantic import BaseModel, Field


class InterviewQuestionOutput(BaseModel):
    question: str
    category: str = Field(description="One of: technical, behavioral, project, system_design, role_specific")


class InterviewQuestionsOutput(BaseModel):
    questions: list[InterviewQuestionOutput] = Field(default_factory=list)


class InterviewAnswerOutput(BaseModel):
    answer: str
    situation: str | None = None
    task: str | None = None
    action: str | None = None
    result: str | None = None
