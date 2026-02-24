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

      const token = localStorage.getItem("spotify_token");
      if (!token) {
        setError("Spotify token missing.");
        return;
      }

      // Search track
      const searchRes = await fetch(
        `https://api.spotify.com/v1/search?q=track:${encodeURIComponent(trackName)} artist:${encodeURIComponent(artistName)}&type=track&limit=1`,
        { headers: { Authorization: `Bearer ${token}` } }
      );
      const searchData = await searchRes.json();
      if (!searchData.tracks.items.length) throw new Error("Track not found");

      const trackId = searchData.tracks.items[0].id;

      // Call backend
      const backendRes = await fetch("/next-track", {
        method: "POST",
        headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
        body: JSON.stringify({ seed_track_id: trackId, year: 2020, window: 5 }),
      });

      if (!backendRes.ok) {
        const errData = await backendRes.json();
        throw new Error(errData.detail || "Backend error");
      }

      const data = await backendRes.json();
      setResult(data);
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
