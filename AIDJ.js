import { useState, useEffect } from "react";

export default function AIDJ() {
  const [trackName, setTrackName] = useState("");
  const [artistName, setArtistName] = useState("");
  const [seedTrack, setSeedTrack] = useState(null);
  const [nextTrack, setNextTrack] = useState(null);
  const [year, setYear] = useState(null);
  const [error, setError] = useState("");

  const handleSubmit = async (e) => {
    e.preventDefault();
    try {
      setError("");

      // 1️⃣ Search Track
      const searchRes = await fetch("/api/search", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ track_name: trackName, artist_name: artistName }),
      });
      if (!searchRes.ok) throw new Error("Track search failed");
      const track = await searchRes.json();
      setSeedTrack(track);

      // 2️⃣ Extract release year
      const releaseYear = parseInt(track.album.release_date.slice(0, 4));
      setYear(releaseYear);

      // 3️⃣ Get next track
      const nextRes = await fetch("/api/next-track", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ seed_track_id: track.id, year: releaseYear, window: 5 }),
      });
      if (!nextRes.ok) throw new Error("Next track fetch failed");
      const nextData = await nextRes.json();
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
          onChange={e => setTrackName(e.target.value)}
          required
        />
        <input
          placeholder="Artist Name"
          value={artistName}
          onChange={e => setArtistName(e.target.value)}
          required
        />
        <button type="submit">Find Transitions</button>
      </form>

      {error && <p style={{ color: "red" }}>{error}</p>}

      {seedTrack && (
        <div>
          <p><strong>Seed Track:</strong> {seedTrack.name}</p>
          <p><strong>Year:</strong> {year}</p>
        </div>
      )}

      {nextTrack && (
        <div>
          <p><strong>Next Track ID:</strong> {nextTrack.next_track_id}</p>
          <p><strong>Score:</strong> {nextTrack.score}</p>
          <p><strong>Reason:</strong> {nextTrack.reason}</p>
        </div>
      )}
    </div>
  );
}
