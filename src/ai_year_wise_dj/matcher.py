from __future__ import annotations

from ai_year_wise_dj.models import TrackFingerprint, TransitionCandidate


def _distance(a: float, b: float) -> float:
    return abs(a - b)


def _section_score(from_fp: TrackFingerprint, from_idx: int, to_fp: TrackFingerprint, to_idx: int) -> float:
    energy_penalty = _distance(from_fp.section_energies[from_idx], to_fp.section_energies[to_idx])
    tempo_penalty = _distance(from_fp.section_tempos[from_idx], to_fp.section_tempos[to_idx])
    loudness_penalty = _distance(from_fp.section_loudness[from_idx], to_fp.section_loudness[to_idx])

    weighted_penalty = (0.5 * energy_penalty) + (0.3 * tempo_penalty) + (0.2 * loudness_penalty)
    return max(0.0, 1.0 - weighted_penalty)


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
    enforce_same_year: bool = True,
) -> TransitionCandidate | None:
    best: TransitionCandidate | None = None

    # When the seed track has no audio features (e.g. Spotify returned 403),
    # fall back to metadata-based matching to avoid scoring fake zero values.
    use_metadata = not current.has_audio_features

    for candidate in candidates:
        if candidate.track_id == current.track_id:
            continue
        if enforce_same_year and candidate.release_year != current.release_year:
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
