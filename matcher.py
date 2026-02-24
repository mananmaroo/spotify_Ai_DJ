from models import TrackFingerprint, TransitionCandidate

def best_transition(current: TrackFingerprint, candidates: list[TrackFingerprint], target_year: int = 0, window: int = 2):
    best = None
    use_metadata = not current.has_audio_features

    for c in candidates:
        if c.track_id == current.track_id:
            continue
        score = 1.0
        reason = f"Year diff: {abs(c.release_year - target_year)}"
        match = TransitionCandidate(from_track_id=current.track_id, to_track_id=c.track_id, score=score, reason=reason)
        if best is None or match.score > best.score:
            best = match
    return best
