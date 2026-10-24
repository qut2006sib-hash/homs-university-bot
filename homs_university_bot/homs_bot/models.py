"""Stored records. Question, intent, and answer are different ids on purpose."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Source:
    id: str
    title: str
    issuer: str
    reference: str | None
    article_or_page: str | None
    effective_from: str | None
    effective_to: str | None
    review_status: str
    is_synthetic: bool


@dataclass
class Intent:
    id: str
    code: str
    title_ar: str
    description_ar: str | None
    status: str
    is_synthetic: bool


@dataclass
class QuestionVariant:
    id: str
    intent_id: str
    wording: str
    normalized_wording: str
    status: str
    is_synthetic: bool


@dataclass
class Answer:
    id: str
    intent_id: str
    source_id: str | None
    body_ar: str
    status: str
    faculty_code: str | None
    academic_year: str | None
    study_system: str | None
    specialization_code: str | None
    effective_from: str | None
    effective_to: str | None
    version: int
    supersedes_answer_id: str | None
    is_synthetic: bool


@dataclass
class StudentContext:
    telegram_user_id: int
    faculty_code: str | None = None
    academic_year: str | None = None
    study_system: str | None = None
    specialization_code: str | None = None


@dataclass
class QuestionRow:
    id: str
    intent_id: str
    intent_code: str
    intent_title: str
    wording: str
    normalized_wording: str
    is_synthetic: bool


@dataclass
class Interaction:
    id: int
    telegram_user_id: int | None
    original_text: str
    normalized_text: str
    question_id: str | None
    intent_id: str | None
    answer_id: str | None
    outcome: str
    similarity_score: float | None
    needs_review: bool
    review_status: str
    candidate_intent_ids: str | None


@dataclass
class Feedback:
    id: int
    interaction_id: int
    telegram_user_id: int | None
    verdict: str
    review_status: str
    admin_note: str | None


@dataclass
class Button:
    kind: str
    label: str
    intent_id: str | None = None
    field: str | None = None
    value: str | None = None


@dataclass
class AskResult:
    outcome: str
    text: str
    authoritative: bool = False
    synthetic: bool = False
    interaction_id: int | None = None
    score: float | None = None
    intent_id: str | None = None
    intent_code: str | None = None
    intent_title: str | None = None
    question_id: str | None = None
    answer_id: str | None = None
    sources: list[dict] = field(default_factory=list)
    buttons: list[Button] = field(default_factory=list)
    needs_review: bool = False
