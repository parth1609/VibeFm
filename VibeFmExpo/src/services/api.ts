import {
  Song,
  AudioStreamInfo,
  LoadPlaylistRequest,
  LoadPlaylistResponse,
  NextSongResponse
} from '../types';

// React Native has fetch globally available
declare const fetch: any;

const API_BASE_URL = __DEV__
  ? 'http://10.12.139.231:8000'
  : 'https://vibefm.onrender.com'; // Update this to your production backend URL

class ApiService {
  private baseUrl: string;

  constructor(baseUrl: string = API_BASE_URL) {
    this.baseUrl = baseUrl;
    console.log('API Service initialized with baseUrl:', this.baseUrl);
  }

  private async request<T>(
    endpoint: string,
    options: any = {}
  ): Promise<T> {
    const url = `${this.baseUrl}${endpoint}`;

    const defaultHeaders = {
      'Content-Type': 'application/json',
    };

    const config = {
      ...options,
      headers: {
        ...defaultHeaders,
        ...options.headers,
      },
    };

    try {
      const response = await fetch(url, config);

      if (!response.ok) {
        const errorText = await response.text();
        console.error(`API Error: ${response.status} - ${errorText}`);
        throw new Error(`HTTP error! status: ${response.status}`);
      }

      return await response.json();
    } catch (error) {
      console.error('API request failed:', error instanceof Error ? error.message : 'Unknown error');
      throw error;
    }
  }

  async loadPlaylist(request: LoadPlaylistRequest): Promise<LoadPlaylistResponse> {
    return this.request<LoadPlaylistResponse>('/playlist/load', {
      method: 'POST',
      body: JSON.stringify(request),
    });
  }

  async getNextSong(): Promise<NextSongResponse> {
    return this.request<NextSongResponse>('/playlist/next');
  }

  async getStreamInfo(videoId: string): Promise<AudioStreamInfo> {
    return this.request<AudioStreamInfo>(`/playlist/stream/${videoId}`);
  }

  async getQueue(): Promise<Song[]> {
    return this.request<Song[]>('/playlist/queue');
  }

  getAudioUrl(videoId: string): string {
    return `${this.baseUrl}/playlist/audio/${videoId}`;
  }
}

export const apiService = new ApiService();
