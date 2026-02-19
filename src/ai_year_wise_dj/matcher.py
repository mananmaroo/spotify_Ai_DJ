from __future__ import annotations

from ai_year_wise_dj.models import TrackFingerprint, TransitionCandidate

# Maximum duration difference (ms) treated as fully dissimilar — two minutes.
_MAX_DURATION_DIFF_MS = 120_000


def _score_transition(
    current: TrackFingerprint,
    candidate: TrackFingerprint,
    target_year: int,
    window: int,
) -> tuple[float, str]:
    pop_diff = abs(current.popularity - candidate.popularity)
    pop_score = max(0.0, 1.0 - pop_diff / 100.0)

    dur_diff = abs(current.duration_ms - candidate.duration_ms)
    dur_score = max(0.0, 1.0 - dur_diff / _MAX_DURATION_DIFF_MS)

    year_diff = abs(candidate.release_year - target_year)
    year_score = max(0.0, 1.0 - year_diff / max(window, 1))

    total = 0.5 * pop_score + 0.2 * dur_score + 0.3 * year_score
    reason = (
        f"popularityΔ={pop_diff}, "
        f"yearΔ={year_diff}, "
        f"durationΔ={dur_diff}ms"
    )
    return total, reason


def best_transition(
    current: TrackFingerprint,
    candidates: list[TrackFingerprint],
    target_year: int,
    window: int = 2,
) -> TransitionCandidate | None:
    best: TransitionCandidate | None = None

    for candidate in candidates:
        if candidate.track_id == current.track_id:
            continue

        score, reason = _score_transition(current, candidate, target_year, window)
        match = TransitionCandidate(
            from_track_id=current.track_id,
            to_track_id=candidate.track_id,
            score=score,
            reason=reason,
        )
        if best is None or match.score > best.score:
            best = match
    return best
