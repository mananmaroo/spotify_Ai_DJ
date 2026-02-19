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


def _metadata_score(from_fp: TrackFingerprint, to_fp: TrackFingerprint) -> tuple[float, str]:
    """Score a transition using track metadata (popularity, duration) when audio features
    are unavailable due to Spotify API restrictions."""
    popularity_penalty = _distance(from_fp.popularity, to_fp.popularity) / 100.0
    # Normalise duration difference: cap at 60 s (60_000 ms) to keep it in [0, 1]
    duration_penalty = min(1.0, _distance(from_fp.duration_ms, to_fp.duration_ms) / 60_000.0)
    score = max(0.0, 1.0 - 0.6 * popularity_penalty - 0.4 * duration_penalty)
    reason = (
        f"popularityΔ={abs(from_fp.popularity - to_fp.popularity)}, "
        f"durationΔ={abs(from_fp.duration_ms - to_fp.duration_ms) / 1000:.1f}s"
    )
    return score, reason


def best_transition(
    current: TrackFingerprint,
    candidates: list[TrackFingerprint],
    target_year: int,
    window: int = 2,
) -> TransitionCandidate | None:
    best: TransitionCandidate | None = None

    # When the seed track has no audio features (e.g. Spotify returned 403),
    # fall back to metadata-based matching to avoid scoring fake zero values.
    use_metadata = not current.has_audio_features

    for candidate in candidates:
        if candidate.track_id == current.track_id:
            continue

        if use_metadata:
            score, reason = _metadata_score(current, candidate)
            match = TransitionCandidate(
                from_track_id=current.track_id,
                to_track_id=candidate.track_id,
                from_section_index=0,
                to_section_index=0,
                score=score,
                reason=reason,
            )
        elif not candidate.has_audio_features:
            # Seed has audio features but this candidate doesn't — skip to
            # avoid scoring fake fallback zeros as a perfect match.
            continue
        else:
            match = None
            for from_idx in range(len(current.section_energies)):
                for to_idx in range(len(candidate.section_energies)):
                    score = _section_score(current, from_idx, candidate, to_idx)
                    reason = (
                        f"energyΔ={_distance(current.section_energies[from_idx], candidate.section_energies[to_idx]):.3f}, "
                        f"tempoΔ={_distance(current.section_tempos[from_idx], candidate.section_tempos[to_idx]):.3f}, "
                        f"loudnessΔ={_distance(current.section_loudness[from_idx], candidate.section_loudness[to_idx]):.3f}"
                    )
                    candidate_match = TransitionCandidate(
                        from_track_id=current.track_id,
                        to_track_id=candidate.track_id,
                        from_section_index=from_idx,
                        to_section_index=to_idx,
                        score=score,
                        reason=reason,
                    )
                    if match is None or candidate_match.score > match.score:
                        match = candidate_match

        if match is not None and (best is None or match.score > best.score):
            best = match
    return best
