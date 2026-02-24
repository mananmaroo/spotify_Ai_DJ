import React, { useEffect, useState } from "react";
import { login, getTokenFromUrl } from "./spotifyAuth";
import { initializePlayer } from "./player";

function App() {
  const [token, setToken] = useState(null);
  const [seedTrack, setSeedTrack] = useState("");

  useEffect(() => {
    const t = getTokenFromUrl();
    if (t) {
      setToken(t);
      initializePlayer(t, handleTrackEnd);
    }
  }, []);

  const handleTrackEnd = async (currentTrackId) => {
    const res = await fetch("http://localhost:8000/next-track", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "Authorization": `Bearer ${token}`
      },
      body: JSON.stringify({
        seed_track_id: currentTrackId,
        year: 2018,
        window: 5
      })
    });

    const data = await res.json();
    playTrack(data.next_track_id);
  };

  const playTrack = (trackId) => {
    fetch(`https://api.spotify.com/v1/me/player/play`, {
      method: "PUT",
      headers: {
        "Authorization": `Bearer ${token}`,
        "Content-Type": "application/json"
      },
      body: JSON.stringify({
        uris: [`spotify:track:${trackId}`]
      })
    });
  };

  if (!token) {
    return <button onClick={login}>Login with Spotify</button>;
  }

  return (
    <div>
      <h1>AI Yearwise DJ</h1>
      <input
        placeholder="Enter Spotify Track ID"
        value={seedTrack}
        onChange={e => setSeedTrack(e.target.value)}
      />
      <button onClick={() => playTrack(seedTrack)}>Start DJ</button>
    </div>
  );
}

export default App;
