import React, {
  forwardRef,
  useEffect,
  useImperativeHandle,
  useRef,
} from 'react';
import { Platform, View } from 'react-native';

/**
 * Audio engine for the web build.
 *
 * The deployed backend cannot stream from YouTube (the host's IP gets the
 * datacenter bot check), but the listener's own connection can. This mounts a
 * hidden YouTube embed and drives it through the official iframe API, so the
 * track plays from the browser instead of through the server.
 */

export type YouTubeAudioHandle = {
  load: (videoId: string, autoplay: boolean) => void;
  play: () => void;
  pause: () => void;
  seekToMs: (ms: number) => void;
};

type EmbedState = {
  positionMs: number;
  durationMs: number;
  playing: boolean;
  buffering: boolean;
};

type Props = {
  onState: (state: EmbedState) => void;
  onEnded: () => void;
  onError: (message: string) => void;
};

const isWeb = Platform.OS === 'web';

function getWindow(): any | null {
  return typeof window === 'undefined' ? null : (window as any);
}

function loadIframeApi(): Promise<any> {
  const win = getWindow();
  if (!win) return Promise.reject(new Error('No window on this platform.'));
  if (win.YT && win.YT.Player) return Promise.resolve(win.YT);

  // One script tag for the whole app, however many times we ask for it.
  if (!win.__vibefmYouTubeApi) {
    win.__vibefmYouTubeApi = new Promise((resolve: (yt: any) => void) => {
      const previous = win.onYouTubeIframeAPIReady;
      win.onYouTubeIframeAPIReady = () => {
        if (typeof previous === 'function') previous();
        resolve(win.YT);
      };
      const script = win.document.createElement('script');
      script.src = 'https://www.youtube.com/iframe_api';
      win.document.head.appendChild(script);
    });
  }
  return win.__vibefmYouTubeApi;
}

const YouTubeAudio = forwardRef<YouTubeAudioHandle, Props>(
  function YouTubeAudio({ onState, onEnded, onError }, ref) {
    const containerRef = useRef<any>(null);
    const playerRef = useRef<any>(null);
    const pendingRef = useRef<{ videoId: string; autoplay: boolean } | null>(null);

    // The iframe callbacks are registered once, so reach the latest props via a ref.
    const handlersRef = useRef({ onState, onEnded, onError });
    handlersRef.current = { onState, onEnded, onError };

    useEffect(() => {
      if (!isWeb) return undefined;

      // The iframe API reports state changes but not the play head.
      const timer = setInterval(() => {
        const player = playerRef.current;
        if (!player || typeof player.getCurrentTime !== 'function') return;
        const durationMs = Math.round((player.getDuration?.() || 0) * 1000);
        const positionMs = Math.round((player.getCurrentTime?.() || 0) * 1000);
        const playerState = player.getPlayerState?.();
        if (durationMs > 0 || positionMs > 0) {
          handlersRef.current.onState({
            positionMs,
            durationMs,
            playing: playerState === 1,
            buffering: playerState === 3,
          });
        }
      }, 500);

      return () => clearInterval(timer);
    }, []);

    useEffect(() => {
      if (!isWeb) return undefined;
      let cancelled = false;

      loadIframeApi()
        .then((YT) => {
          if (cancelled || !containerRef.current) return;
          playerRef.current = new YT.Player(containerRef.current, {
            height: '1',
            width: '1',
            playerVars: {
              playsinline: 1,
              controls: 0,
              disablekb: 1,
              origin: getWindow()?.location?.origin,
            },
            events: {
              onReady: () => {
                const pending = pendingRef.current;
                if (!pending) return;
                pendingRef.current = null;
                playerRef.current?.loadVideoById(pending.videoId);
                if (pending.autoplay) playerRef.current?.playVideo();
              },
              onStateChange: (event: any) => {
                const player = playerRef.current;
                handlersRef.current.onState({
                  positionMs: Math.round((player?.getCurrentTime?.() || 0) * 1000),
                  durationMs: Math.round((player?.getDuration?.() || 0) * 1000),
                  playing: event.data === 1,
                  buffering: event.data === 3,
                });
                if (event.data === 0) handlersRef.current.onEnded();
              },
              onError: (event: any) => {
                handlersRef.current.onError(
                  event?.data === 101 || event?.data === 150
                    ? 'This track does not allow embedded playback.'
                    : `YouTube playback error (${event?.data ?? 'unknown'}).`
                );
              },
            },
          });
        })
        .catch(() =>
          handlersRef.current.onError('Could not start the YouTube player.')
        );

      return () => {
        cancelled = true;
        try {
          playerRef.current?.destroy?.();
        } catch {
          // Player already gone.
        }
        playerRef.current = null;
      };
    }, []);

    useImperativeHandle(
      ref,
      () => ({
        load: (videoId: string, autoplay: boolean) => {
          const player = playerRef.current;
          if (!player || typeof player.loadVideoById !== 'function') {
            // The API is still loading: play it as soon as the player is ready.
            pendingRef.current = { videoId, autoplay };
            return;
          }
          player.loadVideoById(videoId);
          if (autoplay) player.playVideo();
        },
        play: () => playerRef.current?.playVideo?.(),
        pause: () => playerRef.current?.pauseVideo?.(),
        seekToMs: (ms: number) =>
          playerRef.current?.seekTo?.(Math.max(0, ms / 1000), true),
      }),
      []
    );

    if (!isWeb) return null;

    return (
      <View
        ref={containerRef as any}
        style={{
          position: 'absolute',
          width: 1,
          height: 1,
          opacity: 0,
          overflow: 'hidden',
        }}
        pointerEvents="none"
      />
    );
  }
);

export default YouTubeAudio;
