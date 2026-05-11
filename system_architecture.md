# VibeFm — System Architecture

> **Project:** AI Personal Radio Station (VibeFm / VibeCast)
> **Version:** 1.0 — Initial Architecture Proposal

---

## 1. Architecture Overview

VibeFm is built around a **real-time audio broadcast pipeline** that stitches together music audio (from YouTube), AI-generated RJ voice segments (LLM + TTS), and live data (weather, news) into a seamless, radio-like experience — personalized per user and shareable via a unique URL.

The system follows a **hybrid client-server** model:
- Heavy processing (audio fetching, LLM calls, TTS synthesis) happens **server-side**
- Playback and UI rendering happen **client-side**
- A **pre-generation buffer** ensures zero-gap transitions (key UX requirement)

---

## 2. High-Level Architecture Diagram

```mermaid
graph TD
    subgraph Client ["🖥️ Client (Browser / PWA)"]
        UI["React / Next.js UI\n(Radio Player, Station Page)"]
        AudioCtx["Web Audio API\n(Playback Engine)"]
        UI --> AudioCtx
    end

    subgraph BFF ["⚡ Backend For Frontend (Next.js API Routes / FastAPI)"]
        StationAPI["Station API\n/station/:freq"]
        PlaylistAPI["Playlist Service\n/playlist/fetch"]
        RJ_Engine["RJ Script Engine\n/rj/generate"]
        AdEngine["Ad Engine\n/ads/inject"]
        ShareAPI["Share / Frequency API\n/share/:userId"]
    end

    subgraph ExternalAPIs ["🌐 External APIs"]
        YT_Data["YouTube Data API v3\n(Playlist metadata)"]
        YT_Stream["yt-dlp / ytdl-core\n(Audio stream extraction)"]
        Gemini["Gemini 1.5 Flash\n(LLM — Script Gen)"]
        ElevenLabs["ElevenLabs / Google TTS\n(Voice synthesis)"]
        Weather["OpenWeatherMap API"]
        NewsAPI["NewsAPI.org"]
    end

    subgraph Storage ["🗄️ Storage / Auth"]
        Firestore["Firestore\n(User profiles, playlists,\nplayback state)"]
        Auth["Firebase Auth\n(Google OAuth)"]
        Cache["Redis / Upstash\n(Pre-generated RJ audio cache)"]
        CDN["CDN / GCS Bucket\n(TTS audio files)"]
    end

    UI -->|Station requests| BFF
    BFF --> YT_Data
    BFF --> YT_Stream
    BFF --> Gemini
    BFF --> ElevenLabs
    BFF --> Weather
    BFF --> NewsAPI
    BFF --> Firestore
    BFF --> Auth
    BFF --> Cache
    BFF --> CDN
    AudioCtx -->|Stream audio URL| YT_Stream
    AudioCtx -->|TTS audio URL| CDN
```

---

## 3. Core Subsystems

### 3.1 🎵 Music Engine

The heart of the system — fetches, queues, and streams audio from YouTube.

```mermaid
sequenceDiagram
    participant User
    participant Frontend
    participant PlaylistSvc
    participant YT_DataAPI
    participant YT_Stream

    User->>Frontend: Paste YouTube Playlist URL
    Frontend->>PlaylistSvc: POST /playlist/fetch {url}
    PlaylistSvc->>YT_DataAPI: GET playlistItems (metadata)
    YT_DataAPI-->>PlaylistSvc: [{title, artist, videoId, duration}]
    PlaylistSvc->>PlaylistSvc: Weighted Shuffle Algorithm
    PlaylistSvc-->>Frontend: Ordered Queue [{song1...songN}]
    Frontend->>YT_Stream: Request audioStreamUrl(videoId)
    YT_Stream-->>Frontend: Direct audio stream URL
    Frontend->>Frontend: Play via Web Audio API
```

**Weighted Shuffle Algorithm Logic:**
```
weight(song) = 1 / (1 + times_played_recently)
             × recency_penalty(last_played_timestamp)
             × user_mood_boost (optional future feature)
```
Songs not played in the longest time get the highest weights. Implements a "Discovery within Familiarity" feel.

---

### 3.2 🎙️ AI RJ Pipeline

The most complex subsystem — generates contextual radio commentary and synthesizes voice audio **ahead of time** while music is playing.

```mermaid
sequenceDiagram
    participant MusicEngine
    participant RJ_Scheduler
    participant ContextBuilder
    participant GeminiAPI
    participant TTS_Service
    participant AudioCache

    MusicEngine->>RJ_Scheduler: Song 1 starts playing
    RJ_Scheduler->>ContextBuilder: Fetch context for interlude
    ContextBuilder->>GeminiAPI: {next_songs[], weather, news, persona}
    GeminiAPI-->>ContextBuilder: RJ Script text
    ContextBuilder->>TTS_Service: Synthesize(script, voice_persona)
    TTS_Service-->>AudioCache: Store .mp3 → CDN URL
    Note over MusicEngine,AudioCache: ← All this happens during Song 1, 2, 3 playback
    MusicEngine->>RJ_Scheduler: Song 3 ends
    RJ_Scheduler-->>MusicEngine: Play pre-cached RJ audio URL
    MusicEngine->>MusicEngine: Seamless transition ✅
```

**Gemini Prompt Architecture:**
```
System: You are {persona} — a radio host with {tone} personality.
        Keep scripts under 45 seconds. Be natural, not robotic.

Context:
  - Songs just played: [{song1}, {song2}, {song3}]
  - Up next: [{song4}, {song5}]
  - Current weather in {city}: {temp}, {condition}
  - Top news: {headline_1}, {headline_2}
  - Ad slot: {sponsor_script | null}

Generate a radio interlude script.
```

---

### 3.3 📡 Station & Sharing System

Each user gets a unique **"Frequency"** — a shareable URL that lets friends tune into your personalized station in real-time (or near real-time).

```mermaid
graph LR
    A["User creates station\n/station/create"] --> B["Generate unique freq ID\ne.g. 98.7-xyz-abc"]
    B --> C["Store in Firestore:\n{freq_id, userId, playlistId,\ncurrent_song_index, rj_persona}"]
    C --> D["Share URL: vibefm.app/tune/98.7-xyz-abc"]
    D --> E["Friend visits URL"]
    E --> F["Fetch station state\n(current song + position)"]
    F --> G["Sync playback\n(same song, same position)"]
    G --> H["Same RJ voice & AI segments"]
```

> **Note:** True real-time sync (like radio) requires a WebSocket or SSE connection to push state updates to listeners. Start with polling for simplicity.

---

### 3.4 📢 Ad Engine

Ad segments are injected as part of the RJ script — not as separate audio breaks.

```mermaid
graph TD
    AdEngine["Ad Engine"]
    AdEngine -->|Check| Timer{"15-20 min elapsed\nor N songs played?"}
    Timer -->|Yes| FetchAd["Fetch active sponsor script\nfrom Firestore/Config"]
    Timer -->|No| Skip["Skip injection"]
    FetchAd --> InjectPrompt["Inject into Gemini RJ Prompt:\n'This segment is sponsored by {Brand}...'"]
    InjectPrompt --> NaturalRead["RJ reads it naturally in voice"]
    NaturalRead --> Seamless["Seamless ad experience ✅"]
```

---

## 4. Data Models

### User Profile (`/users/{userId}`)
```json
{
  "userId": "uid_abc123",
  "displayName": "Parth",
  "email": "parth@example.com",
  "freq_id": "98.7-xyz-abc",
  "rj_persona": "chill_indie_host",
  "news_interests": ["Tech", "Sports"],
  "location": { "city": "Mumbai", "lat": 19.07, "lon": 72.87 },
  "created_at": "2026-04-25T11:00:00Z"
}
```

### Playlist State (`/stations/{freq_id}`)
```json
{
  "freq_id": "98.7-xyz-abc",
  "owner_id": "uid_abc123",
  "playlist_url": "https://youtube.com/playlist?list=...",
  "songs": [
    { "videoId": "abc", "title": "Blinding Lights", "artist": "The Weeknd", "duration": 200, "play_count": 3, "last_played": "2026-04-24T..." }
  ],
  "current_index": 4,
  "queued_rj_audio_url": "https://cdn.vibefm.app/rj/uid_abc123_20260425.mp3",
  "last_rj_at": "2026-04-25T10:45:00Z"
}
```

### Ad Config (`/ads/active`)
```json
{
  "sponsor": "Notion",
  "script_template": "This hour is brought to you by Notion — the all-in-one workspace...",
  "active": true,
  "placement_interval_songs": 6
}
```

---

## 5. Infrastructure & Deployment

```mermaid
graph TD
    subgraph Hosting
        Vercel["Vercel\n(Next.js Frontend + API Routes)"]
    end
    subgraph Backend
        FastAPI["FastAPI Workers\n(Heavy: yt-dlp, TTS jobs)"]
        BullMQ["BullMQ / Cloud Tasks\n(Async TTS generation queue)"]
    end
    subgraph Storage
        Firebase["Firebase\n(Auth + Firestore)"]
        GCS["Google Cloud Storage\n(TTS .mp3 files)"]
        Upstash["Upstash Redis\n(Caching + Job Queue)"]
    end

    Vercel -->|Lightweight API calls| Firebase
    Vercel -->|Offload heavy tasks| FastAPI
    FastAPI -->|Enqueue TTS jobs| BullMQ
    BullMQ -->|Store output| GCS
    FastAPI -->|Cache results| Upstash
```

| Concern | Solution |
|---|---|
| Frontend Hosting | **Vercel** (Next.js, free tier viable) |
| API / Heavy Processing | **FastAPI on Railway or Render** (yt-dlp needs a server environment) |
| Database | **Firestore** (schemaless, real-time capable) |
| Auth | **Firebase Auth** (Google OAuth, frictionless) |
| TTS Audio Storage | **Google Cloud Storage + CDN** |
| Async Job Queue | **Upstash Redis + BullMQ** (pre-generate RJ audio) |
| Caching | **Upstash Redis** (API responses: weather, news, metadata) |

---

## 6. Key Technical Decisions & Trade-offs

| Decision | Chosen Approach | Rationale |
|---|---|---|
| **YouTube Playback** | YouTube IFrame API (not yt-dlp streaming) | ToS compliance; yt-dlp for server-side metadata only |
| **RJ Audio Pre-gen** | Async queue + CDN storage | Eliminates playback gaps (core UX requirement) |
| **LLM Model** | Gemini 1.5 Flash | Low latency + generous free quota for MVP |
| **TTS Provider** | ElevenLabs (MVP) → Google TTS (Scale) | ElevenLabs quality wins early users; switch at cost threshold |
| **Sharing Sync** | Polling (MVP) → WebSockets (V2) | Simpler to build; upgrade path clear |
| **Database** | Firestore | Real-time listeners built-in; perfect for station state sync |

---

## 7. Phased Implementation Roadmap

```mermaid
gantt
    title VibeFm Build Phases
    dateFormat  YYYY-MM-DD
    section Phase 1 — Music Engine
    YouTube Playlist Fetch     :p1a, 2026-05-01, 7d
    Weighted Shuffle Algorithm :p1b, after p1a, 5d
    Basic Player UI            :p1c, after p1a, 7d

    section Phase 2 — AI RJ
    Gemini Script Generation   :p2a, after p1b, 7d
    TTS Integration            :p2b, after p2a, 5d
    Pre-gen Buffer Pipeline    :p2c, after p2b, 7d

    section Phase 3 — Live Data & Personas
    Weather + News integration :p3a, after p2c, 5d
    RJ Persona Selection       :p3b, after p3a, 4d

    section Phase 4 — Social & Ads
    Frequency / Share URLs     :p4a, after p3b, 5d
    Ad Engine                  :p4b, after p4a, 5d
    Station sync (Polling)     :p4c, after p4b, 4d
```

---

## 8. Critical Path & Risks

| Risk | Impact | Mitigation |
|---|---|---|
| **YouTube ToS violation** | High | Use IFrame API; restrict to personal use in ToS |
| **ElevenLabs API cost at scale** | Medium | Cache all TTS; switch to Google TTS after 1K users |
| **yt-dlp breaks (YouTube patches)** | Medium | Fall back to IFrame API only; monitor yt-dlp releases |
| **LLM latency > song length** | High | Trigger RJ generation 2 songs early; use streaming TTS |
| **Real-time sync complexity** | Medium | Start with polling; WebSockets only in V2 |

