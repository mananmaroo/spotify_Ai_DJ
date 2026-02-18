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


def best_transition(
    current: TrackFingerprint,
    candidates: list[TrackFingerprint],
    enforce_same_year: bool = True,
) -> TransitionCandidate | None:
    best: TransitionCandidate | None = None

    for candidate in candidates:
        if candidate.track_id == current.track_id:
            continue
        if enforce_same_year and candidate.release_year != current.release_year:
            continue

        for from_idx in range(len(current.section_energies)):
            for to_idx in range(len(candidate.section_energies)):
                score = _section_score(current, from_idx, candidate, to_idx)
                reason = (
                    f"energyΔ={_distance(current.section_energies[from_idx], candidate.section_energies[to_idx]):.3f}, "
                    f"tempoΔ={_distance(current.section_tempos[from_idx], candidate.section_tempos[to_idx]):.3f}, "
                    f"loudnessΔ={_distance(current.section_loudness[from_idx], candidate.section_loudness[to_idx]):.3f}"
                )
                match = TransitionCandidate(
                    from_track_id=current.track_id,
                    to_track_id=candidate.track_id,
                    from_section_index=from_idx,
                    to_section_index=to_idx,
                    score=score,
                    reason=reason,
                )
                if best is None or match.score > best.score:
                    best = match
    return best
