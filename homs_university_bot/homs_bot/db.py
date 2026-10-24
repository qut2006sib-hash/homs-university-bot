"""SQLite storage. Student interactions are rows of their own, not question variants."""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from homs_bot.models import (
    Answer,
    Feedback,
    Intent,
    Interaction,
    QuestionRow,
    QuestionVariant,
    Source,
    StudentContext,
)
from homs_bot.text_norm import normalize_arabic

SCHEMA = """
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS sources (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    issuer TEXT NOT NULL,
    reference TEXT,
    article_or_page TEXT,
    effective_from TEXT,
    effective_to TEXT,
    review_status TEXT NOT NULL CHECK (review_status IN ('draft', 'approved', 'retired')),
    is_synthetic INTEGER NOT NULL DEFAULT 0 CHECK (is_synthetic IN (0, 1)),
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS intents (
    id TEXT PRIMARY KEY,
    code TEXT NOT NULL UNIQUE,
    title_ar TEXT NOT NULL,
    description_ar TEXT,
    status TEXT NOT NULL CHECK (status IN ('draft', 'approved', 'retired')),
    is_synthetic INTEGER NOT NULL DEFAULT 0 CHECK (is_synthetic IN (0, 1)),
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS question_variants (
    id TEXT PRIMARY KEY,
    intent_id TEXT NOT NULL REFERENCES intents(id),
    wording TEXT NOT NULL,
    normalized_wording TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('draft', 'approved', 'retired')),
    is_synthetic INTEGER NOT NULL DEFAULT 0 CHECK (is_synthetic IN (0, 1)),
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS answers (
    id TEXT PRIMARY KEY,
    intent_id TEXT NOT NULL REFERENCES intents(id),
    source_id TEXT REFERENCES sources(id),
    body_ar TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('draft', 'approved', 'retired')),
    faculty_code TEXT,
    academic_year TEXT,
    study_system TEXT,
    specialization_code TEXT,
    effective_from TEXT,
    effective_to TEXT,
    version INTEGER NOT NULL DEFAULT 1,
    supersedes_answer_id TEXT REFERENCES answers(id),
    is_synthetic INTEGER NOT NULL DEFAULT 0 CHECK (is_synthetic IN (0, 1)),
    created_at TEXT NOT NULL,
    retired_at TEXT
);

CREATE TABLE IF NOT EXISTS student_contexts (
    telegram_user_id INTEGER PRIMARY KEY,
    faculty_code TEXT,
    academic_year TEXT,
    study_system TEXT,
    specialization_code TEXT,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS interactions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    telegram_user_id INTEGER,
    original_text TEXT NOT NULL,
    normalized_text TEXT NOT NULL,
    question_id TEXT REFERENCES question_variants(id),
    intent_id TEXT REFERENCES intents(id),
    answer_id TEXT REFERENCES answers(id),
    outcome TEXT NOT NULL,
    similarity_score REAL,
    candidate_intent_ids TEXT,
    needs_review INTEGER NOT NULL DEFAULT 0 CHECK (needs_review IN (0, 1)),
    review_status TEXT NOT NULL DEFAULT 'pending'
        CHECK (review_status IN ('pending', 'reviewed', 'dismissed')),
    parent_interaction_id INTEGER REFERENCES interactions(id),
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS feedback (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    interaction_id INTEGER NOT NULL REFERENCES interactions(id) ON DELETE CASCADE,
    telegram_user_id INTEGER,
    verdict TEXT NOT NULL CHECK (verdict IN ('helpful', 'incorrect')),
    review_status TEXT NOT NULL DEFAULT 'pending'
        CHECK (review_status IN ('pending', 'reviewed')),
    admin_note TEXT,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS clarification_choices (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    interaction_id INTEGER NOT NULL REFERENCES interactions(id) ON DELETE CASCADE,
    offered_intent_ids TEXT NOT NULL,
    chosen_intent_id TEXT,
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_questions_intent ON question_variants(intent_id);
CREATE INDEX IF NOT EXISTS idx_answers_intent ON answers(intent_id);
CREATE INDEX IF NOT EXISTS idx_interactions_review ON interactions(needs_review, review_status);
CREATE INDEX IF NOT EXISTS idx_feedback_review ON feedback(review_status);
"""


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def connect(path: str) -> sqlite3.Connection:
    if path != ":memory:":
        Path(path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA)
    conn.commit()


def open_store(path: str) -> "Store":
    conn = connect(path)
    init_db(conn)
    return Store(conn)


def _flag(value: object) -> int:
    return 1 if value else 0


def _clean(value: str | None) -> str | None:
    if value is None:
        return None
    value = str(value).strip()
    return value or None


class Store:
    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def add_source(
        self,
        *,
        id: str,
        title: str,
        issuer: str,
        reference: str | None = None,
        article_or_page: str | None = None,
        effective_from: str | None = None,
        effective_to: str | None = None,
        review_status: str = "draft",
        is_synthetic: bool = False,
    ) -> None:
        self.conn.execute(
            """
            INSERT INTO sources (
                id, title, issuer, reference, article_or_page,
                effective_from, effective_to, review_status, is_synthetic, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                title = excluded.title,
                issuer = excluded.issuer,
                reference = excluded.reference,
                article_or_page = excluded.article_or_page,
                effective_from = excluded.effective_from,
                effective_to = excluded.effective_to,
                review_status = excluded.review_status,
                is_synthetic = excluded.is_synthetic
            """,
            (
                id,
                title,
                issuer,
                reference,
                article_or_page,
                effective_from,
                effective_to,
                review_status,
                _flag(is_synthetic),
                utc_now(),
            ),
        )
        self.conn.commit()

    def add_intent(
        self,
        *,
        id: str,
        code: str,
        title_ar: str,
        description_ar: str | None = None,
        status: str = "draft",
        is_synthetic: bool = False,
    ) -> None:
        self.conn.execute(
            """
            INSERT INTO intents (
                id, code, title_ar, description_ar, status, is_synthetic, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                code = excluded.code,
                title_ar = excluded.title_ar,
                description_ar = excluded.description_ar,
                status = excluded.status,
                is_synthetic = excluded.is_synthetic
            """,
            (id, code, title_ar, description_ar, status, _flag(is_synthetic), utc_now()),
        )
        self.conn.commit()

    def add_question(
        self,
        *,
        id: str,
        intent_id: str,
        wording: str,
        status: str = "draft",
        is_synthetic: bool = False,
    ) -> str:
        self.conn.execute(
            """
            INSERT INTO question_variants (
                id, intent_id, wording, normalized_wording, status, is_synthetic, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                intent_id = excluded.intent_id,
                wording = excluded.wording,
                normalized_wording = excluded.normalized_wording,
                status = excluded.status,
                is_synthetic = excluded.is_synthetic
            """,
            (
                id,
                intent_id,
                wording,
                normalize_arabic(wording),
                status,
                _flag(is_synthetic),
                utc_now(),
            ),
        )
        self.conn.commit()
        return id

    def add_answer(
        self,
        *,
        id: str,
        intent_id: str,
        body_ar: str,
        source_id: str | None = None,
        status: str = "draft",
        faculty_code: str | None = None,
        academic_year: str | None = None,
        study_system: str | None = None,
        specialization_code: str | None = None,
        effective_from: str | None = None,
        effective_to: str | None = None,
        version: int = 1,
        supersedes_answer_id: str | None = None,
        is_synthetic: bool = False,
    ) -> None:
        self.conn.execute(
            """
            INSERT INTO answers (
                id, intent_id, source_id, body_ar, status,
                faculty_code, academic_year, study_system, specialization_code,
                effective_from, effective_to, version, supersedes_answer_id,
                is_synthetic, created_at, retired_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                intent_id = excluded.intent_id,
                source_id = excluded.source_id,
                body_ar = excluded.body_ar,
                status = excluded.status,
                faculty_code = excluded.faculty_code,
                academic_year = excluded.academic_year,
                study_system = excluded.study_system,
                specialization_code = excluded.specialization_code,
                effective_from = excluded.effective_from,
                effective_to = excluded.effective_to,
                version = excluded.version,
                supersedes_answer_id = excluded.supersedes_answer_id,
                is_synthetic = excluded.is_synthetic,
                retired_at = excluded.retired_at
            """,
            (
                id,
                intent_id,
                source_id,
                body_ar,
                status,
                _clean(faculty_code),
                _clean(academic_year),
                _clean(study_system),
                _clean(specialization_code),
                effective_from,
                effective_to,
                version,
                supersedes_answer_id,
                _flag(is_synthetic),
                utc_now(),
                utc_now() if status == "retired" else None,
            ),
        )
        self.conn.commit()

    def get_source(self, source_id: str) -> Source | None:
        row = self.conn.execute("SELECT * FROM sources WHERE id = ?", (source_id,)).fetchone()
        return _source(row) if row else None

    def get_intent(self, intent_id: str) -> Intent | None:
        row = self.conn.execute("SELECT * FROM intents WHERE id = ?", (intent_id,)).fetchone()
        return _intent(row) if row else None

    def get_intent_by_code(self, code: str) -> Intent | None:
        row = self.conn.execute("SELECT * FROM intents WHERE code = ?", (code,)).fetchone()
        return _intent(row) if row else None

    def get_question(self, question_id: str) -> QuestionVariant | None:
        row = self.conn.execute(
            "SELECT * FROM question_variants WHERE id = ?", (question_id,)
        ).fetchone()
        return _question(row) if row else None

    def get_answer(self, answer_id: str) -> Answer | None:
        row = self.conn.execute("SELECT * FROM answers WHERE id = ?", (answer_id,)).fetchone()
        return _answer(row) if row else None

    def list_sources(self) -> list[Source]:
        rows = self.conn.execute("SELECT * FROM sources ORDER BY id").fetchall()
        return [_source(row) for row in rows]

    def list_intents(self) -> list[Intent]:
        rows = self.conn.execute("SELECT * FROM intents ORDER BY code").fetchall()
        return [_intent(row) for row in rows]

    def list_questions(self, intent_id: str | None = None) -> list[QuestionVariant]:
        if intent_id:
            rows = self.conn.execute(
                "SELECT * FROM question_variants WHERE intent_id = ? ORDER BY id",
                (intent_id,),
            ).fetchall()
        else:
            rows = self.conn.execute("SELECT * FROM question_variants ORDER BY id").fetchall()
        return [_question(row) for row in rows]

    def list_answers_by_intent(self, intent_id: str) -> list[Answer]:
        rows = self.conn.execute(
            "SELECT * FROM answers WHERE intent_id = ? ORDER BY version, id",
            (intent_id,),
        ).fetchall()
        return [_answer(row) for row in rows]

    def list_matchable_questions(self, allow_synthetic: bool) -> list[QuestionRow]:
        rows = self.conn.execute(
            """
            SELECT
                q.id, q.intent_id, q.wording, q.normalized_wording, q.is_synthetic,
                i.code AS intent_code, i.title_ar AS intent_title
            FROM question_variants q
            JOIN intents i ON i.id = q.intent_id
            WHERE q.status = 'approved'
              AND i.status = 'approved'
              AND (? = 1 OR (q.is_synthetic = 0 AND i.is_synthetic = 0))
            """,
            (_flag(allow_synthetic),),
        ).fetchall()
        return [
            QuestionRow(
                id=row["id"],
                intent_id=row["intent_id"],
                intent_code=row["intent_code"],
                intent_title=row["intent_title"],
                wording=row["wording"],
                normalized_wording=row["normalized_wording"],
                is_synthetic=bool(row["is_synthetic"]),
            )
            for row in rows
        ]

    def list_answers_with_sources(self, intent_id: str) -> list[tuple[Answer, Source | None]]:
        rows = self.conn.execute(
            """
            SELECT
                a.id AS a_id, a.intent_id, a.source_id, a.body_ar, a.status AS a_status,
                a.faculty_code, a.academic_year, a.study_system, a.specialization_code,
                a.effective_from AS a_from, a.effective_to AS a_to,
                a.version, a.supersedes_answer_id, a.is_synthetic AS a_syn,
                s.id AS s_id, s.title, s.issuer, s.reference, s.article_or_page,
                s.effective_from AS s_from, s.effective_to AS s_to,
                s.review_status AS s_status, s.is_synthetic AS s_syn
            FROM answers a
            LEFT JOIN sources s ON s.id = a.source_id
            WHERE a.intent_id = ?
            ORDER BY a.version, a.id
            """,
            (intent_id,),
        ).fetchall()
        pairs: list[tuple[Answer, Source | None]] = []
        for row in rows:
            answer = Answer(
                id=row["a_id"],
                intent_id=row["intent_id"],
                source_id=row["source_id"],
                body_ar=row["body_ar"],
                status=row["a_status"],
                faculty_code=row["faculty_code"],
                academic_year=row["academic_year"],
                study_system=row["study_system"],
                specialization_code=row["specialization_code"],
                effective_from=row["a_from"],
                effective_to=row["a_to"],
                version=row["version"],
                supersedes_answer_id=row["supersedes_answer_id"],
                is_synthetic=bool(row["a_syn"]),
            )
            source = None
            if row["s_id"]:
                source = Source(
                    id=row["s_id"],
                    title=row["title"],
                    issuer=row["issuer"],
                    reference=row["reference"],
                    article_or_page=row["article_or_page"],
                    effective_from=row["s_from"],
                    effective_to=row["s_to"],
                    review_status=row["s_status"],
                    is_synthetic=bool(row["s_syn"]),
                )
            pairs.append((answer, source))
        return pairs

    def set_question_status(self, question_id: str, status: str) -> None:
        self.conn.execute(
            "UPDATE question_variants SET status = ? WHERE id = ?",
            (status, question_id),
        )
        self.conn.commit()

    def set_answer_status(self, answer_id: str, status: str) -> None:
        retired_at = utc_now() if status == "retired" else None
        self.conn.execute(
            "UPDATE answers SET status = ?, retired_at = ? WHERE id = ?",
            (status, retired_at, answer_id),
        )
        self.conn.commit()

    def set_intent_status(self, intent_id: str, status: str) -> None:
        self.conn.execute(
            "UPDATE intents SET status = ? WHERE id = ?",
            (status, intent_id),
        )
        self.conn.commit()

    def get_context(self, user_id: int) -> StudentContext | None:
        row = self.conn.execute(
            "SELECT * FROM student_contexts WHERE telegram_user_id = ?",
            (user_id,),
        ).fetchone()
        if not row:
            return None
        return StudentContext(
            telegram_user_id=row["telegram_user_id"],
            faculty_code=row["faculty_code"],
            academic_year=row["academic_year"],
            study_system=row["study_system"],
            specialization_code=row["specialization_code"],
        )

    def save_context(self, ctx: StudentContext) -> None:
        self.conn.execute(
            """
            INSERT INTO student_contexts (
                telegram_user_id, faculty_code, academic_year, study_system,
                specialization_code, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(telegram_user_id) DO UPDATE SET
                faculty_code = excluded.faculty_code,
                academic_year = excluded.academic_year,
                study_system = excluded.study_system,
                specialization_code = excluded.specialization_code,
                updated_at = excluded.updated_at
            """,
            (
                ctx.telegram_user_id,
                _clean(ctx.faculty_code),
                _clean(ctx.academic_year),
                _clean(ctx.study_system),
                _clean(ctx.specialization_code),
                utc_now(),
            ),
        )
        self.conn.commit()

    def delete_student(self, user_id: int) -> None:
        self.conn.execute("DELETE FROM feedback WHERE telegram_user_id = ?", (user_id,))
        self.conn.execute(
            """
            DELETE FROM clarification_choices
            WHERE interaction_id IN (
                SELECT id FROM interactions WHERE telegram_user_id = ?
            )
            """,
            (user_id,),
        )
        self.conn.execute("DELETE FROM interactions WHERE telegram_user_id = ?", (user_id,))
        self.conn.execute(
            "DELETE FROM student_contexts WHERE telegram_user_id = ?",
            (user_id,),
        )
        self.conn.commit()

    def add_interaction(
        self,
        *,
        telegram_user_id: int | None,
        original_text: str,
        normalized_text: str,
        outcome: str,
        question_id: str | None = None,
        intent_id: str | None = None,
        answer_id: str | None = None,
        similarity_score: float | None = None,
        candidate_intent_ids: str | None = None,
        needs_review: bool = False,
        parent_interaction_id: int | None = None,
    ) -> int:
        cur = self.conn.execute(
            """
            INSERT INTO interactions (
                telegram_user_id, original_text, normalized_text, question_id, intent_id,
                answer_id, outcome, similarity_score, candidate_intent_ids, needs_review,
                review_status, parent_interaction_id, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'pending', ?, ?)
            """,
            (
                telegram_user_id,
                original_text,
                normalized_text,
                question_id,
                intent_id,
                answer_id,
                outcome,
                similarity_score,
                candidate_intent_ids,
                _flag(needs_review),
                parent_interaction_id,
                utc_now(),
            ),
        )
        self.conn.commit()
        return int(cur.lastrowid)

    def get_interaction(self, interaction_id: int) -> Interaction | None:
        row = self.conn.execute(
            "SELECT * FROM interactions WHERE id = ?",
            (interaction_id,),
        ).fetchone()
        return _interaction(row) if row else None

    def set_interaction_review(self, interaction_id: int, status: str) -> None:
        self.conn.execute(
            "UPDATE interactions SET review_status = ? WHERE id = ?",
            (status, interaction_id),
        )
        self.conn.commit()

    def list_review_queue(self) -> list[Interaction]:
        rows = self.conn.execute(
            """
            SELECT * FROM interactions
            WHERE needs_review = 1 AND review_status = 'pending'
            ORDER BY id
            """
        ).fetchall()
        return [_interaction(row) for row in rows]

    def list_recent_interactions(self, user_id: int | None = None, limit: int = 12) -> list[Interaction]:
        if user_id is None:
            rows = self.conn.execute(
                "SELECT * FROM interactions ORDER BY id DESC LIMIT ?",
                (limit,),
            ).fetchall()
        else:
            rows = self.conn.execute(
                "SELECT * FROM interactions WHERE telegram_user_id = ? ORDER BY id DESC LIMIT ?",
                (user_id, limit),
            ).fetchall()
        return [_interaction(row) for row in rows]

    def add_feedback(self, *, interaction_id: int, user_id: int | None, verdict: str) -> int:
        cur = self.conn.execute(
            """
            INSERT INTO feedback (
                interaction_id, telegram_user_id, verdict, review_status, created_at
            ) VALUES (?, ?, ?, 'pending', ?)
            """,
            (interaction_id, user_id, verdict, utc_now()),
        )
        self.conn.commit()
        return int(cur.lastrowid)

    def list_pending_feedback(self) -> list[Feedback]:
        rows = self.conn.execute(
            "SELECT * FROM feedback WHERE review_status = 'pending' ORDER BY id"
        ).fetchall()
        return [_feedback(row) for row in rows]

    def list_recent_feedback(self, user_id: int | None = None, limit: int = 12) -> list[Feedback]:
        if user_id is None:
            rows = self.conn.execute(
                "SELECT * FROM feedback ORDER BY id DESC LIMIT ?",
                (limit,),
            ).fetchall()
        else:
            rows = self.conn.execute(
                "SELECT * FROM feedback WHERE telegram_user_id = ? ORDER BY id DESC LIMIT ?",
                (user_id, limit),
            ).fetchall()
        return [_feedback(row) for row in rows]

    def resolve_feedback(self, feedback_id: int, note: str) -> None:
        self.conn.execute(
            """
            UPDATE feedback
            SET review_status = 'reviewed', admin_note = ?
            WHERE id = ?
            """,
            (note, feedback_id),
        )
        self.conn.commit()

    def get_feedback(self, feedback_id: int) -> Feedback | None:
        row = self.conn.execute("SELECT * FROM feedback WHERE id = ?", (feedback_id,)).fetchone()
        return _feedback(row) if row else None

    def add_clarification(
        self,
        *,
        interaction_id: int,
        offered_intent_ids: list[str],
        chosen_intent_id: str | None,
    ) -> None:
        self.conn.execute(
            """
            INSERT INTO clarification_choices (
                interaction_id, offered_intent_ids, chosen_intent_id, created_at
            ) VALUES (?, ?, ?, ?)
            """,
            (interaction_id, ",".join(offered_intent_ids), chosen_intent_id, utc_now()),
        )
        self.conn.commit()

    def count_intents(self) -> int:
        row = self.conn.execute("SELECT COUNT(*) AS n FROM intents").fetchone()
        return int(row["n"])


def _source(row: sqlite3.Row) -> Source:
    return Source(
        id=row["id"],
        title=row["title"],
        issuer=row["issuer"],
        reference=row["reference"],
        article_or_page=row["article_or_page"],
        effective_from=row["effective_from"],
        effective_to=row["effective_to"],
        review_status=row["review_status"],
        is_synthetic=bool(row["is_synthetic"]),
    )


def _intent(row: sqlite3.Row) -> Intent:
    return Intent(
        id=row["id"],
        code=row["code"],
        title_ar=row["title_ar"],
        description_ar=row["description_ar"],
        status=row["status"],
        is_synthetic=bool(row["is_synthetic"]),
    )


def _question(row: sqlite3.Row) -> QuestionVariant:
    return QuestionVariant(
        id=row["id"],
        intent_id=row["intent_id"],
        wording=row["wording"],
        normalized_wording=row["normalized_wording"],
        status=row["status"],
        is_synthetic=bool(row["is_synthetic"]),
    )


def _answer(row: sqlite3.Row) -> Answer:
    return Answer(
        id=row["id"],
        intent_id=row["intent_id"],
        source_id=row["source_id"],
        body_ar=row["body_ar"],
        status=row["status"],
        faculty_code=row["faculty_code"],
        academic_year=row["academic_year"],
        study_system=row["study_system"],
        specialization_code=row["specialization_code"],
        effective_from=row["effective_from"],
        effective_to=row["effective_to"],
        version=row["version"],
        supersedes_answer_id=row["supersedes_answer_id"],
        is_synthetic=bool(row["is_synthetic"]),
    )


def _interaction(row: sqlite3.Row) -> Interaction:
    score = row["similarity_score"]
    return Interaction(
        id=row["id"],
        telegram_user_id=row["telegram_user_id"],
        original_text=row["original_text"],
        normalized_text=row["normalized_text"],
        question_id=row["question_id"],
        intent_id=row["intent_id"],
        answer_id=row["answer_id"],
        outcome=row["outcome"],
        similarity_score=float(score) if score is not None else None,
        needs_review=bool(row["needs_review"]),
        review_status=row["review_status"],
        candidate_intent_ids=row["candidate_intent_ids"],
    )


def _feedback(row: sqlite3.Row) -> Feedback:
    return Feedback(
        id=row["id"],
        interaction_id=row["interaction_id"],
        telegram_user_id=row["telegram_user_id"],
        verdict=row["verdict"],
        review_status=row["review_status"],
        admin_note=row["admin_note"],
    )
