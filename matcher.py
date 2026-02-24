# matcher.py
from __future__ import annotations
from typing import List, Optional
from models import TrackFingerprint, TransitionCandidate

# Maximum duration difference in ms considered fully dissimilar (~2 minutes)
_MAX_DURATION_DIFF_MS = 120_000

def _distance(a: float, b: float) -> float:
    """Simple absolute difference."""
    return abs(a - b)

def _score_transition(
    current: TrackFingerprint,
    candidate: TrackFingerprint,
    target_year: int,
    window: int,
) -> tuple[float, str]:
    """Score a candidate track against current track based on metadata."""
    # Popularity score
    pop_diff = abs(current.popularity - candidate.popularity)
    pop_score = max(0.0, 1.0 - pop_diff / 100.0)

    # Duration score
    dur_diff = abs(current.duration_ms - candidate.duration_ms)
    dur_score = max(0.0, 1.0 - dur_diff / _MAX_DURATION_DIFF_MS)

    # Year score
    year_diff = abs(candidate.release_year - target_year)
    year_score = max(0.0, 1.0 - year_diff / max(window, 1))

    # Weighted total
    total_score = 0.5 * pop_score + 0.2 * dur_score + 0.3 * year_score
    reason = f"popularityΔ={pop_diff}, yearΔ={year_diff}, durationΔ={dur_diff}ms"
    return total_score, reason

def _metadata_score(from_fp: TrackFingerprint, to_fp: TrackFingerprint) -> tuple[float, str]:
    """Fallback scoring when audio features are missing."""
    popularity_penalty = _distance(from_fp.popularity, to_fp.popularity) / 100.0
    duration_penalty = min(1.0, _distance(from_fp.duration_ms, to_fp.duration_ms) / 60_000.0)
    score = max(0.0, 1.0 - 0.6 * popularity_penalty - 0.4 * duration_penalty)
    reason = f"popularityΔ={abs(from_fp.popularity - to_fp.popularity)}, durationΔ={abs(from_fp.duration_ms - to_fp.duration_ms)/1000:.1f}s"
    return score, reason

def best_transition(
    current: TrackFingerprint,
    candidates: List[TrackFingerprint],
    target_year: int = 0,
    window: int = 2,
    enforce_same_year: bool = True,
) -> Optional[TransitionCandidate]:
    """
    Choose the best track transition from a list of candidates.
    
    :param current: Current track fingerprint
    :param candidates: List of candidate fingerprints
    :param target_year: Target release year
    :param window: Year window for scoring
    :param enforce_same_year: If True, penalize tracks outside the year window
    :return: TransitionCandidate or None
    """
    best: Optional[TransitionCandidate] = None
    use_metadata = not current.has_audio_features

    for candidate in candidates:
        if candidate.track_id == current.track_id:
            continue

        if use_metadata:
            score, reason = _metadata_score(current, candidate)
        elif not candidate.has_audio_features:
            # Skip candidates without audio if current has audio features
            continue
        elif enforce_same_year:
            score, reason = _score_transition(current, candidate, target_year, window)
        else:
            score, reason = _metadata_score(current, candidate)

        match = TransitionCandidate(
            from_track_id=current.track_id,
            to_track_id=candidate.track_id,
            score=score,
            reason=reason,
        )

        if best is None or match.score > best.score:
            best = match

    return best
