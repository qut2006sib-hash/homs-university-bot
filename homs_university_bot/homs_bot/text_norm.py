"""Arabic normalization for matching. The original student wording is stored separately."""

from __future__ import annotations

import re
import unicodedata

# Diacritics and Quranic marks. Removed so تشكيل does not change a match.
_TASHKEEL = re.compile(r"[\u0610-\u061A\u064B-\u065F\u0670\u06D6-\u06ED]")
# After character folding, keep letters, digits, and spaces only.
_CLEAN = re.compile(r"[^0-9a-z\u0621-\u063f\u0641-\u064a\s]+")
_SPACE = re.compile(r"\s+")

_FOLDS = str.maketrans(
    {
        "أ": "ا",
        "إ": "ا",
        "آ": "ا",
        "ٱ": "ا",
        "ى": "ي",
        "ئ": "ي",
        "ؤ": "و",
        "ة": "ه",
        "٠": "0",
        "١": "1",
        "٢": "2",
        "٣": "3",
        "٤": "4",
        "٥": "5",
        "٦": "6",
        "٧": "7",
        "٨": "8",
        "٩": "9",
    }
)


def normalize_arabic(text: str) -> str:
    """Fold common spelling differences. Does not translate dialect into formal Arabic."""
    if not text:
        return ""
    folded = unicodedata.normalize("NFKC", text)
    folded = folded.replace("ـ", "")
    folded = _TASHKEEL.sub("", folded)
    folded = folded.translate(_FOLDS).lower()
    folded = _CLEAN.sub(" ", folded)
    return _SPACE.sub(" ", folded).strip()
