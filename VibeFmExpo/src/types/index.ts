export interface Song {
  video_id: string;
  title: string;
  artist: string;
  duration_sec: number;
  thumbnail_url?: string;
  play_count: number;
  last_played_at?: string;
  audio_stream_url?: string;
}

export interface AudioStreamInfo {
  video_id: string;
  stream_url: string;
  ext: string;
  abr?: number;
  duration_sec?: number;
  title: string;
  uploader: string;
  http_headers: Record<string, string>;
}

export interface LoadPlaylistRequest {
  url: string;
  queue_size?: number;
}

export interface LoadPlaylistResponse {
  total_songs: number;
  queue: Song[];
}

export interface NextSongResponse {
  song: Song;
  stream: AudioStreamInfo;
  playback_url: string;
}
