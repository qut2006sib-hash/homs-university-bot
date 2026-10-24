"""Student-context labels. These are navigation choices, not university rules."""

from __future__ import annotations

import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

CATALOG_PATH = Path(__file__).resolve().parent.parent / "data" / "catalog.json"

CONSTRAINT_FIELDS = (
    "faculty_code",
    "academic_year",
    "study_system",
    "specialization_code",
)

FIELD_LABELS_AR = {
    "faculty_code": "الكلية",
    "academic_year": "السنة الدراسية",
    "study_system": "نظام الدراسة",
    "specialization_code": "الاختصاص",
}

OTHER_CODE = "other"


@dataclass(frozen=True)
class Labeled:
    code: str
    label: str


@dataclass(frozen=True)
class Catalog:
    faculties: tuple[Labeled, ...]
    years: tuple[Labeled, ...]
    study_systems: tuple[Labeled, ...]
    specializations: dict[str, tuple[Labeled, ...]]
    other_label: str

    def faculty(self, code: str | None) -> Labeled | None:
        return _find(self.faculties, code)

    def year(self, code: str | None) -> Labeled | None:
        return _find(self.years, code)

    def study_system(self, code: str | None) -> Labeled | None:
        return _find(self.study_systems, code)

    def specialization(self, faculty_code: str | None, code: str | None) -> Labeled | None:
        if not faculty_code or not code:
            return None
        return _find(self.specializations.get(faculty_code, ()), code)

    def has_specializations(self, faculty_code: str | None) -> bool:
        return bool(faculty_code and self.specializations.get(faculty_code))

    def label_for(self, field: str, code: str | None, faculty_code: str | None = None) -> str:
        if not code:
            return "غير محدد"
        if code == OTHER_CODE:
            return self.other_label
        if field == "faculty_code":
            found = self.faculty(code)
        elif field == "academic_year":
            found = self.year(code)
        elif field == "study_system":
            found = self.study_system(code)
        elif field == "specialization_code":
            found = self.specialization(faculty_code, code)
        else:
            found = None
        return found.label if found else code

    def choices(self, field: str, faculty_code: str | None = None) -> tuple[Labeled, ...]:
        if field == "faculty_code":
            return self.faculties
        if field == "academic_year":
            return self.years
        if field == "study_system":
            return self.study_systems
        if field == "specialization_code":
            return self.specializations.get(faculty_code or "", ())
        return ()


def _find(items: tuple[Labeled, ...], code: str | None) -> Labeled | None:
    if not code:
        return None
    for item in items:
        if item.code == code:
            return item
    return None


@lru_cache(maxsize=1)
def load_catalog() -> Catalog:
    data = json.loads(CATALOG_PATH.read_text(encoding="utf-8"))
    specs = {
        faculty: tuple(Labeled(item["code"], item["label"]) for item in rows)
        for faculty, rows in data.get("specializations", {}).items()
    }
    return Catalog(
        faculties=tuple(Labeled(item["code"], item["label"]) for item in data["faculties"]),
        years=tuple(Labeled(item["code"], item["label"]) for item in data["years"]),
        study_systems=tuple(
            Labeled(item["code"], item["label"]) for item in data["studySystems"]
        ),
        specializations=specs,
        other_label=data.get("otherLabel", "غير ذلك"),
    )
