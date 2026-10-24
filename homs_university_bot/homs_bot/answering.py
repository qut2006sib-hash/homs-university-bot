"""Choose an approved answer for one intent, or ask only for a field that would change it."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

from homs_bot.catalog import CONSTRAINT_FIELDS, OTHER_CODE
from homs_bot.models import Answer, Source, StudentContext


@dataclass
class Selection:
    kind: str
    pairs: list[tuple[Answer, Source]] = field(default_factory=list)
    field_name: str | None = None
    options: list[str] = field(default_factory=list)


def _parse_day(value: str | None) -> date | None:
    if not value:
        return None
    return date.fromisoformat(value)


def _window_ok(start: str | None, end: str | None, today: date) -> bool:
    try:
        start_day = _parse_day(start)
        end_day = _parse_day(end)
    except ValueError:
        return False
    if start_day and today < start_day:
        return False
    if end_day and today > end_day:
        return False
    return True


def _constraint(answer: Answer, name: str) -> str | None:
    value = getattr(answer, name)
    if value is None:
        return None
    value = str(value).strip()
    return value or None


def specificity(answer: Answer) -> int:
    return sum(1 for name in CONSTRAINT_FIELDS if _constraint(answer, name))


def contradicts(answer: Answer, ctx: StudentContext) -> bool:
    for name in CONSTRAINT_FIELDS:
        required = _constraint(answer, name)
        have = getattr(ctx, name)
        if required and have and required != have:
            return True
    return False


def missing_fields(answer: Answer, ctx: StudentContext) -> list[str]:
    missing: list[str] = []
    for name in CONSTRAINT_FIELDS:
        required = _constraint(answer, name)
        if required and not getattr(ctx, name):
            missing.append(name)
    return missing


def _eligible(
    pairs: list[tuple[Answer, Source | None]],
    today: date,
    allow_synthetic: bool,
) -> list[tuple[Answer, Source]]:
    usable: list[tuple[Answer, Source]] = []
    for answer, source in pairs:
        if answer.status != "approved" or source is None:
            continue
        if source.review_status != "approved":
            continue
        synthetic = answer.is_synthetic or source.is_synthetic
        if synthetic and not allow_synthetic:
            continue
        if not _window_ok(answer.effective_from, answer.effective_to, today):
            continue
        if not _window_ok(source.effective_from, source.effective_to, today):
            continue
        usable.append((answer, source))
    # A newer version replaces the one it supersedes once it is itself servable,
    # so the old text keeps answering until the new one takes effect.
    superseded = {answer.supersedes_answer_id for answer, _source in usable if answer.supersedes_answer_id}
    usable = [pair for pair in usable if pair[0].id not in superseded]
    real = [pair for pair in usable if not (pair[0].is_synthetic or pair[1].is_synthetic)]
    return real or usable


def _could_change(
    answer: Answer,
    best_specificity: int,
    best_bodies: set[str],
) -> bool:
    body = answer.body_ar.strip()
    spec = specificity(answer)
    if spec > best_specificity and body not in best_bodies:
        return True
    if spec == best_specificity and body not in best_bodies:
        return True
    return False


def _discriminating_field(partials: list[tuple[Answer, Source]], ctx: StudentContext) -> str:
    counts = {name: 0 for name in CONSTRAINT_FIELDS}
    for answer, _source in partials:
        for name in missing_fields(answer, ctx):
            counts[name] += 1
    present = [name for name in CONSTRAINT_FIELDS if counts[name] > 0]
    return max(present, key=lambda name: (counts[name], -CONSTRAINT_FIELDS.index(name)))


def _options_for(field_name: str, partials: list[tuple[Answer, Source]]) -> list[str]:
    values: list[str] = []
    for answer, _source in partials:
        required = _constraint(answer, field_name)
        if required and required not in values:
            values.append(required)
    if OTHER_CODE not in values:
        values.append(OTHER_CODE)
    return values


def select_answer(
    pairs: list[tuple[Answer, Source | None]],
    ctx: StudentContext,
    today: date,
    allow_synthetic: bool,
) -> Selection:
    """Return one authoritative set, a context question, a conflict, or nothing.

    Draft, retired, not-yet-effective, and expired rows are ignored. If two
    equally specific approved texts still apply, the case is flagged instead
    of picking a winner.
    """
    pool = [
        pair
        for pair in _eligible(pairs, today, allow_synthetic)
        if not contradicts(pair[0], ctx)
    ]
    if not pool:
        return Selection(kind="none")

    full = [pair for pair in pool if not missing_fields(pair[0], ctx)]
    partial = [pair for pair in pool if missing_fields(pair[0], ctx)]

    if full:
        best_specificity = max(specificity(answer) for answer, _source in full)
        best_bodies = {
            answer.body_ar.strip()
            for answer, _source in full
            if specificity(answer) == best_specificity
        }
    else:
        best_specificity = -1
        best_bodies = set()

    relevant = [
        pair
        for pair in partial
        if _could_change(pair[0], best_specificity, best_bodies)
    ]
    if relevant:
        field_name = _discriminating_field(relevant, ctx)
        return Selection(
            kind="need_context",
            field_name=field_name,
            options=_options_for(field_name, relevant),
        )

    if not full:
        return Selection(kind="none")

    top = [pair for pair in full if specificity(pair[0]) == best_specificity]
    bodies = {answer.body_ar.strip() for answer, _source in top}
    if len(bodies) > 1:
        return Selection(kind="conflict", pairs=top)
    return Selection(kind="answer", pairs=top)
