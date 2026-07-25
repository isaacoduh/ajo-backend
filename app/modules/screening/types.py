"""Screening shared types."""

from dataclasses import dataclass
from datetime import date


@dataclass(frozen=True)
class ScreeningHit:
    source: str
    score: int
    reason: str


@dataclass(frozen=True)
class ScreeningSubject:
    name: str
    dob: date | None
    country: str

