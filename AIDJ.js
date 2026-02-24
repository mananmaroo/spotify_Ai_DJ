import { useState } from "react";

export default function AIDJ() {
  const [trackName, setTrackName] = useState("");
  const [artistName, setArtistName] = useState("");
  const [result, setResult] = useState(null);
  const [error, setError] = useState("");

  const handleSubmit = async (e) => {
    e.preventDefault();
    try {
      setError("");
      setResult(null);

      // Search track via backend
      const searchRes = await fetch("/api/search", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ track_name: trackName, artist_name: artistName }),
      });
      if (!searchRes.ok) {
        const errData = await searchRes.json();
        throw new Error(errData.detail || "Track search failed");
      }
      const searchData = await searchRes.json();
      const trackId = searchData.id;

      // Get next track
      const backendRes = await fetch("/next-track", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ seed_track_id: trackId, year: 2020, window: 5 }),
      });

      if (!backendRes.ok) {
        const errData = await backendRes.json();
        throw new Error(errData.detail || "Next track request failed");
      }

      const nextData = await backendRes.json();
      setResult(nextData);
    } catch (err) {
      console.error(err);
      setError(err.message);
    }
  };

  return (
    <div style={{ maxWidth: 500, margin: "auto", textAlign: "center" }}>
      <h1>🎵 AI DJ</h1>
      <form onSubmit={handleSubmit}>
        <input placeholder="Track Name" value={trackName} onChange={(e) => setTrackName(e.target.value)} required />
        <input placeholder="Artist Name" value={artistName} onChange={(e) => setArtistName(e.target.value)} required />
        <button type="submit">Find Transitions</button>
      </form>

      {error && <p style={{ color: "red" }}>{error}</p>}

      {result && (
        <div>
          <p><strong>Next Track ID:</strong> {result.next_track_id}</p>
          <p><strong>Score:</strong> {result.score}</p>
          <p><strong>Reason:</strong> {result.reason}</p>
        </div>
      )}
    </div>
  );
}
