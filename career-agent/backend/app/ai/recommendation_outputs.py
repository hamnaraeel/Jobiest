"""Structured Ollama output schema for Step 7's recommendation
explanations."""

from pydantic import BaseModel


class ExplanationOutput(BaseModel):
    explanation: str
