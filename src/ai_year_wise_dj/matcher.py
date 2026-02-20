from __future__ import annotations

from ai_year_wise_dj.models import TrackFingerprint, TransitionCandidate

# Fallback year window used when no target year is provided in _metadata_score.
_DEFAULT_YEAR_WINDOW = 10


def _distance(a: float, b: float) -> float:
    return abs(a - b)


def _section_score(
    current: TrackFingerprint,
    from_idx: int,
    candidate: TrackFingerprint,
    to_idx: int,
) -> float:
    energy_score = 1.0 - _distance(current.section_energies[from_idx], candidate.section_energies[to_idx])
    tempo_score = 1.0 - _distance(current.section_tempos[from_idx], candidate.section_tempos[to_idx])
    loudness_score = 1.0 - _distance(current.section_loudness[from_idx], candidate.section_loudness[to_idx])
    return (energy_score + tempo_score + loudness_score) / 3.0


def _score_transition(
    current: TrackFingerprint,
    candidate: TrackFingerprint,
    target_year: int,
    window: int,
) -> tuple[float, str]:
    pop_diff = abs(current.popularity - candidate.popularity)
    pop_score = max(0.0, 1.0 - pop_diff / 100.0)

    year_diff = abs(candidate.release_year - target_year)
    year_score = max(0.0, 1.0 - year_diff / max(window, 1))

    total = 0.5 * pop_score + 0.5 * year_score
    reason = (
        f"popularityΔ={pop_diff}, "
        f"yearΔ={year_diff}"
    )
    return total, reason


def _metadata_score(from_fp: TrackFingerprint, to_fp: TrackFingerprint,
                    target_year: int | None = None, window: int = 2) -> tuple[float, str]:
    """Score a transition using track metadata (popularity, year) when audio features
    are unavailable due to Spotify API restrictions."""
    popularity_penalty = _distance(from_fp.popularity, to_fp.popularity) / 100.0
    if target_year is not None:
        year_diff = abs(to_fp.release_year - target_year)
        year_penalty = min(1.0, year_diff / max(window, 1))
    else:
        year_diff = abs(from_fp.release_year - to_fp.release_year)
        year_penalty = min(1.0, year_diff / _DEFAULT_YEAR_WINDOW)
    score = max(0.0, 1.0 - 0.5 * popularity_penalty - 0.5 * year_penalty)
    reason = (
        f"popularityΔ={abs(from_fp.popularity - to_fp.popularity)}, "
        f"yearΔ={year_diff}"
    )
    return score, reason


def best_transition(
    current: TrackFingerprint,
    candidates: list[TrackFingerprint],
    target_year: int = 0,
    window: int = 2,
    enforce_same_year: bool = True,
) -> TransitionCandidate | None:
    best: TransitionCandidate | None = None

    # When the seed track has no audio features (e.g. Spotify returned 403),
    # fall back to metadata-based matching to avoid scoring fake zero values.
    use_metadata = not current.has_audio_features

    for candidate in candidates:
        if candidate.track_id == current.track_id:
            continue

        if use_metadata:
            score, reason = _metadata_score(current, candidate, target_year, window)
        elif not candidate.has_audio_features:
            # Seed has audio features but this candidate doesn't — skip to
            # avoid scoring fake fallback zeros as a perfect match.
            continue
        elif enforce_same_year:
            score, reason = _score_transition(current, candidate, target_year, window)
        else:
            score, reason = _metadata_score(current, candidate, target_year, window)

        match = TransitionCandidate(
            from_track_id=current.track_id,
            to_track_id=candidate.track_id,
            score=score,
            reason=reason,
        )

        if best is None or match.score > best.score:
            best = match
    return best
