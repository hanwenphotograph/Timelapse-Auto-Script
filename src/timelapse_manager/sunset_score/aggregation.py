"""Validate SunsetScore aggregate values from per-sample scores."""

from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP

from timelapse_manager.sunset_score.models import SampleScore, SunsetRange


def summarize(
    samples: tuple[SampleScore, ...], sampled_count: int
) -> tuple[float, int, bool, tuple[SunsetRange, ...]]:
    high = {sample.sample_index: sample for sample in samples if sample.score >= 3}
    selected: dict[int, SampleScore] = {}
    if sampled_count < 3:
        selected = high
    else:
        for start in range(1, sampled_count - 1):
            matches = [
                high[index] for index in range(start, start + 3) if index in high
            ]
            if len(matches) >= 2:
                selected.update((sample.sample_index, sample) for sample in matches)

    ordered = sorted(selected.values(), key=lambda sample: sample.sample_index)
    ranges: list[SunsetRange] = []
    if ordered:
        first = previous = ordered[0]
        for current in ordered[1:]:
            if current.sample_index == previous.sample_index + 1:
                previous = current
                continue
            ranges.append(SunsetRange(first.photo, previous.photo))
            first = previous = current
        ranges.append(SunsetRange(first.photo, previous.photo))

    scores = [sample.score for sample in samples]
    average = float(
        (Decimal(sum(scores)) / Decimal(len(scores))).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )
    )
    return average, max(scores), bool(selected), tuple(ranges)
