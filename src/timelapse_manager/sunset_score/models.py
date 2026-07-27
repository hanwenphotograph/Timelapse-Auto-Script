"""Typed SunsetScore cache data used by the manager."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class SunsetRange:
    start_photo: str
    end_photo: str


@dataclass(frozen=True)
class SampleScore:
    sample_index: int
    photo: str
    score: int
    reason: str


@dataclass(frozen=True)
class StoredScore:
    application_version: str
    image_count: int
    sampled_count: int
    successful_count: int
    failed_count: int
    interval: int
    average_score: float
    max_score: int
    has_sunset: bool
    sunset_ranges: tuple[SunsetRange, ...]
    samples: tuple[SampleScore, ...]

    @property
    def highest(self) -> SampleScore:
        return next(sample for sample in self.samples if sample.score == self.max_score)


@dataclass(frozen=True)
class SunsetScoreDecision:
    result: StoredScore
    highest_path: Path
    retained_hdr: bool
