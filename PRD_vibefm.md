Product Requirements Document: AI Personal Radio Station

1. Executive Summary

Project Name: AI Personal Radio (Working Title: VibeCast)

Mission: To recreate the nostalgic, lean-back experience of traditional FM radio using a user's own YouTube playlist as the music library, enhanced by an AI Radio Jockey (RJ) that provides context, news, and seamless transitions.

2. Target Audience

Users with "decision fatigue" who have large playlists but don't want to manage them.

People who miss the "live" feel of radio (the human element) but hate commercial radio music choices.

Users who want a personalized news/info update integrated into their music sessions.

3. Functional Requirements

3.1. The Music Engine (Phase 1 Focus)

Playlist Integration: Users provide a YouTube Playlist URL.

The "Radio" Shuffle Algorithm: * Unlike a standard shuffle, the algorithm will use weighted randomness (prioritizing songs not heard recently).

No Skip/Limited Skip: To maintain the "Radio" feel, skipping is either disabled or limited to mimic a linear broadcast.

Audio Streaming: Fetch audio streams from YouTube URLs without video rendering to save bandwidth.

3.2. The AI Radio Jockey (RJ)

Personality Profiles: Users can choose an RJ "Persona" (e.g., "Chill Indie Host," "High-Energy Morning Show," "Deep Voice Late Night").

Dynamic Scripting: Using an LLM (Gemini), the RJ generates a script every 3-4 songs.

Song Transitions: "That was 'Blinding Lights' by The Weeknd. Coming up next, a classic from your 2021 favorites..."

Information Blasts: The AI fetches real-time data via APIs (Weather, News, Horoscopes) and reads them.

TTS Delivery: Convert scripts into high-quality audio using TTS engines (ElevenLabs for realism or Gemini TTS).

3.3. The Ad Engine (Voice-Based)

Native Integration: Ads are not "interruptions" but "segments."

Live-Read Style: The AI RJ reads a provided script from a sponsor, making it sound like a live endorsement (e.g., "This hour is brought to you by 

$$Brand$$

...").

Placement: Inserted every 15-20 minutes of playback or after a specific number of songs.

3.4. Social / Sharing

Station Frequency: Each user gets a unique "Frequency" (URL).

Tune-In: If a friend visits the URL, they hear the owner's playlist and the owner's AI RJ, effectively "listening together" to the owner's taste.

4. Technical Stack (Proposed)

Layer

Technology

Frontend

React or Next.js (Mobile-responsive web app)

Backend

Node.js (Express) or Python (FastAPI)

Music Fetching

YouTube Data API (metadata) + yt-dlp or ytdl-core (audio stream)

LLM (Brain)

Gemini 1.5 Flash (for low-latency script generation)

Voice (TTS)

ElevenLabs API (Premium) / Google Cloud TTS (Scale)

Real-time Data

OpenWeatherMap API, NewsAPI

Storage

Firestore (to save user playlists and playback state)

5. User Flow

Onboarding: User pastes a YouTube Playlist link.

Personalization: User selects RJ voice and "News Interests" (e.g., Tech, Sports).

Tuning In: The "Play" button initiates the broadcast.

The Loop:

RJ Intro (Voice)

Song 1 -> Song 2 -> Song 3

RJ Interlude (Trivia + Weather + Ad)

Song 4...

Sharing: User clicks "Share Station" to give a unique link to a friend.

6. Implementation Challenges & Solutions

Challenge

Proposed Solution

YouTube Terms of Service

Use the official IFrame API for playback where possible, or ensure the app is for personal, non-commercial use to stay within "fair use" research boundaries.

Audio Latency

Pre-generate the AI RJ audio while the current song is playing so there is zero gap between music and voice.

Context Awareness

The LLM must "know" the playlist metadata to talk about the artists correctly. Feed the next 5 songs into the prompt context.

Note on "Choicelessness": 

              The psychological appeal here is "Discovery within Familiarity." The user knows they like the songs (from their playlist), but they don't know which one is coming next, making the experience feel like a curated gift rather than a chore.

7. Success Metrics

Average Session Duration: Goal is > 45 minutes (mimicking long drives/work sessions).

Retention: Users returning to their "Station" daily.

Sharing Rate: Number of users who share their station frequency with others.