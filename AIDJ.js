import { useState } from "react";

export default function AIDJ() {
  const [trackName, setTrackName] = useState("");
  const [artistName, setArtistName] = useState("");
  const [seedTrack, setSeedTrack] = useState(null);
  const [nextTrack, setNextTrack] = useState(null);
  const [year, setYear] = useState(null);
  const [error, setError] = useState("");

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError("");

    try {
      // SEARCH
      const searchRes = await fetch("/api/search", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ track_name: trackName, artist_name: artistName }),
      });

      const track = await searchRes.json();
      if (track.error) throw new Error(track.error);

      setSeedTrack(track);

      const releaseYear = parseInt(track.album.release_date.slice(0, 4));
      setYear(releaseYear);

      // NEXT TRACK
      const nextRes = await fetch("/api/next-track", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          seed_track_id: track.id,
          year: releaseYear,
          window: 5
        }),
      });

      const nextData = await nextRes.json();
      if (nextData.error) throw new Error(nextData.error);

      setNextTrack(nextData);

    } catch (err) {
      console.error(err);
      setError(err.message);
    }
  };

  return (
    <div style={{ maxWidth: 500, margin: "auto", textAlign: "center" }}>
      <h1>🎵 AI DJ</h1>

      <form onSubmit={handleSubmit}>
        <input
          placeholder="Track Name"
          value={trackName}
          onChange={(e) => setTrackName(e.target.value)}
          required
        />
        <input
          placeholder="Artist Name"
          value={artistName}
          onChange={(e) => setArtistName(e.target.value)}
          required
        />
        <button type="submit">Find Transition</button>
      </form>

      {error && <p style={{ color: "red" }}>{error}</p>}

      {seedTrack && (
        <div>
          <h3>Seed Track</h3>
          <p>{seedTrack.name}</p>
          <p>Year: {year}</p>
        </div>
      )}

      {nextTrack && (
        <div>
          <h3>Next Track</h3>
          <p>{nextTrack.name}</p>
          <p>{nextTrack.artists.join(", ")}</p>
          <p>Year: {nextTrack.year}</p>
          <p>Score: {nextTrack.score}</p>
          <p>{nextTrack.reason}</p>
        </div>
      )}
    </div>
  );
}
