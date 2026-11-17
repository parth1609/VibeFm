# VibeFm

Paste a YouTube playlist link and the station plays a random track from it — audio only,
weighted so songs you haven't heard recently come up first.

- `backend/` — FastAPI + yt-dlp audio engine (stream-URL cache, background prefetch, Range-aware proxy)
- `VibeFmExpo/` — Expo / React Native app (iOS, Android, web)

## Run locally

```bash
# Backend API — http://localhost:8000 (interactive docs at /docs)
python main.py

# App — press w for web, scan the QR code for a phone
cd VibeFmExpo && npm install && npx expo start
```

The app derives the API host from the Metro bundler, so a phone on the same Wi-Fi reaches
`http://<your-lan-ip>:8000` automatically. Override with `EXPO_PUBLIC_API_URL` if needed.

## Deploy the backend to Render

The repo already contains everything Render needs: `Dockerfile` (Python 3.13 + ffmpeg),
`requirements.txt`, and a `$PORT`-aware start command. Create a **Web Service → Docker**
pointing at this repository, or let the existing service auto-deploy on every push to `main`.

| Setting | Value |
|---|---|
| Health check path | `/` |
| Port | from `$PORT` (handled by the Dockerfile) |

### Environment variables

| Variable | Purpose |
|---|---|
| `YTDLP_COOKIES` | YouTube cookie file contents (raw or base64). Required on most cloud hosts — see below. |
| `YTDLP_COOKIES_FILE` | Path to a cookie file instead of `YTDLP_COOKIES`. |
| `YTDLP_PROXY` | HTTP/SOCKS proxy used for YouTube requests. Alternative to cookies. |
| `GEMINI_API_KEY` | Only needed by the AI RJ module. |

### YouTube blocks datacenter IPs

Playlist loading works anywhere, but YouTube answers stream requests from cloud IPs
(Render, Fly, AWS, …) with *"Sign in to confirm you're not a bot"*. When that happens the
API returns **503** with that explanation instead of silently failing.

The image already carries the two things a cloud host needs: a current `yt-dlp` (with
`yt-dlp-ejs`) and the **Deno** runtime it uses to solve YouTube's player challenge, plus a
client order (`tv`, `web_embedded`) that does not need a PO token. If YouTube still
refuses the IP, give the server a logged-in YouTube session:

1. Export cookies for `youtube.com` in Netscape format (any "Get cookies.txt" browser extension).
2. Render → your service → **Environment** → add `YTDLP_COOKIES` and paste the file contents
   (base64 also works). Save — Render restarts the service.
3. `GET /playlist/next` should now return a playable `playback_url`.

Running the backend on a home connection needs none of this.

## Audio pipeline

1. `POST /playlist/load` fetches the playlist (flat extraction, ~2 s) and builds a
   weighted-random queue.
2. Stream URLs are resolved lazily, cached for 45 minutes, and pre-warmed for the next two
   tracks so a track change is a memory lookup instead of a 3 s extraction.
3. `GET /playlist/audio/{video_id}` proxies the audio bytes with the required headers,
   forwarding and mirroring `Range` so seeking works.
