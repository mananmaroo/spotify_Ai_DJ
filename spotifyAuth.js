const clientId = "YOUR_SPOTIFY_CLIENT_ID";
const redirectUri = "http://localhost:5173";
const scope = "streaming user-read-email user-read-private user-modify-playback-state user-read-playback-state";

export function login() {
  const authUrl = new URL("https://accounts.spotify.com/authorize");

  authUrl.search = new URLSearchParams({
    response_type: "token",
    client_id: clientId,
    scope,
    redirect_uri: redirectUri,
  }).toString();

  window.location.href = authUrl.toString();
}

export function getTokenFromUrl() {
  const hash = window.location.hash.substring(1);
  const params = new URLSearchParams(hash);
  return params.get("access_token");
}
