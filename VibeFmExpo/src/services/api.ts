import Constants from 'expo-constants';
import {
  AudioStreamInfo,
  LoadPlaylistRequest,
  LoadPlaylistResponse,
  NextSongResponse,
  Song,
} from '../types';

const PRODUCTION_BASE_URL = 'https://vibefm.onrender.com';

/**
 * Work out where the backend lives.
 *
 * In development the API runs on the same machine as the Metro bundler, so we
 * reuse the bundler's hostname. That makes `localhost` work on web/iOS
 * simulator AND the machine's LAN IP work on a real phone — hardcoding
 * `localhost` breaks every physical device.
 *
 * Override with EXPO_PUBLIC_API_URL (e.g. an ngrok URL) when needed.
 */
function resolveBaseUrl(): string {
  const override = process.env.EXPO_PUBLIC_API_URL?.trim();
  if (override) {
    return override.replace(/\/+$/, '');
  }

  if (!__DEV__) {
    return PRODUCTION_BASE_URL;
  }

  const hostUri = Constants.expoConfig?.hostUri;
  const host = hostUri ? hostUri.split(':')[0] : 'localhost';
  return `http://${host || 'localhost'}:8000`;
}

export const API_BASE_URL = resolveBaseUrl();

class ApiService {
  private baseUrl: string;

  constructor(baseUrl: string = API_BASE_URL) {
    this.baseUrl = baseUrl;
  }

  private async request<T>(
    endpoint: string,
    options: RequestInit = {},
    timeoutMs = 20_000
  ): Promise<T> {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), timeoutMs);

    try {
      const response = await fetch(`${this.baseUrl}${endpoint}`, {
        ...options,
        headers: {
          'Content-Type': 'application/json',
          ...(options.headers as Record<string, string> | undefined),
        },
        signal: controller.signal,
      });

      if (!response.ok) {
        let detail = `Request failed (HTTP ${response.status})`;
        try {
          const body = await response.json();
          if (body && typeof body.detail === 'string') {
            detail = body.detail;
          }
        } catch {
          // Response had no JSON body — keep the generic message.
        }
        throw new Error(detail);
      }

      return (await response.json()) as T;
    } catch (error) {
      if (error instanceof Error && error.name === 'AbortError') {
        throw new Error(
          'The station took too long to answer. Check the backend and try again.'
        );
      }
      throw error;
    } finally {
      clearTimeout(timer);
    }
  }

  /** Load a playlist. Big playlists take a while, so give this a long budget. */
  async loadPlaylist(request: LoadPlaylistRequest): Promise<LoadPlaylistResponse> {
    return this.request<LoadPlaylistResponse>(
      '/playlist/load',
      { method: 'POST', body: JSON.stringify(request) },
      120_000
    );
  }

  /** Advance the station's queue and get the next random track. */
  async getNextSong(): Promise<NextSongResponse> {
    return this.request<NextSongResponse>('/playlist/next', {}, 45_000);
  }

  async getStreamInfo(videoId: string): Promise<AudioStreamInfo> {
    return this.request<AudioStreamInfo>(`/playlist/stream/${videoId}`);
  }

  async getQueue(): Promise<Song[]> {
    return this.request<Song[]>('/playlist/queue');
  }

  /** URL of the server-side audio proxy — this is what the player streams. */
  getAudioUrl(videoId: string): string {
    return `${this.baseUrl}/playlist/audio/${videoId}`;
  }

  /** Cheap reachability check used to fail fast with a clear message. */
  async ping(): Promise<boolean> {
    try {
      await this.request<unknown>('/', {}, 6_000);
      return true;
    } catch {
      return false;
    }
  }
}

export const apiService = new ApiService();
