export function initializePlayer(token, onTrackEnd) {
  window.onSpotifyWebPlaybackSDKReady = () => {
    const player = new Spotify.Player({
      name: "AI Yearwise DJ",
      getOAuthToken: cb => { cb(token); },
      volume: 0.8
    });

    player.addListener("player_state_changed", state => {
      if (!state) return;
      if (state.paused && state.position === 0) {
        onTrackEnd(state.track_window.current_track.id);
      }
    });

    player.connect();
    window.spotifyPlayer = player;
  };

  const script = document.createElement("script");
  script.src = "https://sdk.scdn.co/spotify-player.js";
  document.body.appendChild(script);
}
