import React, { useCallback, useEffect, useRef, useState } from 'react';
import {
  ActivityIndicator,
  Dimensions,
  GestureResponderEvent,
  LayoutChangeEvent,
  Pressable,
  StyleSheet,
  Text,
  View,
} from 'react-native';
import { Image } from 'expo-image';
import { MaterialIcons } from '@expo/vector-icons';
import { Audio, AVPlaybackStatus } from 'expo-av';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { StackNavigationProp } from '@react-navigation/stack';
import { apiService } from '../services/api';
import { LoadPlaylistResponse, NextSongResponse } from '../types';
import { colors, borderRadius } from '../styles/colors';

type RootStackParamList = {
  Playlist: undefined;
  Player: { playlist: LoadPlaylistResponse };
  Queue: undefined;
};

type PlayerScreenNavigationProp = StackNavigationProp<RootStackParamList, 'Player'>;

interface Props {
  route: { params: { playlist: LoadPlaylistResponse } };
  navigation: PlayerScreenNavigationProp;
}

/** A fully loaded (but not yet playing) track waiting for the current one to end. */
type StandbyTrack = {
  payload: NextSongResponse;
  sound: Audio.Sound;
};

const ART_SIZE = Math.min(Dimensions.get('window').width * 0.74, 340);

const PlayerScreen: React.FC<Props> = ({ route, navigation }) => {
  const insets = useSafeAreaInsets();
  const { playlist } = route.params;

  const [nowPlaying, setNowPlaying] = useState<NextSongResponse | null>(null);
  const [standby, setStandby] = useState<NextSongResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [isPlaying, setIsPlaying] = useState(false);
  const [isBuffering, setIsBuffering] = useState(false);
  const [positionMs, setPositionMs] = useState(0);
  const [durationMs, setDurationMs] = useState(0);
  const [scrubFraction, setScrubFraction] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);

  const soundRef = useRef<Audio.Sound | null>(null);
  const standbyRef = useRef<StandbyTrack | null>(null);
  const advancingRef = useRef(false);
  const prefetchingRef = useRef(false);
  const mountedRef = useRef(true);
  const seekWidthRef = useRef(0);
  const endHandlerRef = useRef<() => void>(() => {});

  // ---------------------------------------------------------------------
  // Status plumbing
  // ---------------------------------------------------------------------

  const attachStatus = useCallback((sound: Audio.Sound) => {
    // Using setState functions only (stable identities), plus a ref for the
    // track-end handler so this callback never goes stale.
    sound.setOnPlaybackStatusUpdate((status: AVPlaybackStatus) => {
      if (!mountedRef.current) return;

      if (!status.isLoaded) {
        if (status.error) {
          // The stream refused to play (dead source): skip ahead instead of
          // leaving the listener on a silent track.
          setError(status.error);
          if (!advancingRef.current) endHandlerRef.current();
        }
        return;
      }

      setPositionMs(status.positionMillis ?? 0);
      setDurationMs(status.durationMillis ?? 0);
      setIsPlaying(status.isPlaying ?? false);
      setIsBuffering(status.isBuffering ?? false);

      if (status.didJustFinish) {
        endHandlerRef.current();
      }
    });
  }, []);

  // ---------------------------------------------------------------------
  // Playback primitives
  // ---------------------------------------------------------------------

  const playTrack = useCallback(
    async (payload: NextSongResponse, shouldPlay = true) => {
      const previous = soundRef.current;

      const { sound } = await Audio.Sound.createAsync(
        { uri: payload.playback_url },
        {
          shouldPlay,
          isLooping: false,
          progressUpdateIntervalMillis: 250,
          volume: 1,
        }
      );

      soundRef.current = sound;
      attachStatus(sound);

      setNowPlaying(payload);
      setDurationMs(Math.max(0, (payload.song.duration_sec ?? 0) * 1000));
      setPositionMs(0);
      setError(null);

      if (previous) {
        try {
          previous.setOnPlaybackStatusUpdate(null);
          await previous.unloadAsync();
        } catch {
          // Already unloaded — nothing to clean up.
        }
      }
    },
    [attachStatus]
  );

  const loadNextNow = useCallback(async () => {
    setLoading(true);
    setError(null);

    let lastError: unknown = null;
    // A dead video in a playlist should cost one skip, not the whole station.
    for (let attempt = 0; attempt < 3; attempt += 1) {
      try {
        const payload = await apiService.getNextSong();
        if (!mountedRef.current) return;
        await playTrack(payload, true);
        void prefetchNextRef.current();
        setLoading(false);
        return;
      } catch (err) {
        lastError = err;
      }
    }

    if (mountedRef.current) {
      setError(
        lastError instanceof Error
          ? lastError.message
          : 'Could not tune in to this station.'
      );
      setLoading(false);
    }
  }, [playTrack]);

  /**
   * Buffer the next random track while the current one plays, so the
   * transition has no audible gap and no wait for yt-dlp.
   */
  const prefetchNext = useCallback(async () => {
    if (prefetchingRef.current || standbyRef.current) return;
    prefetchingRef.current = true;
    try {
      const payload = await apiService.getNextSong();
      if (!mountedRef.current || standbyRef.current) return;

      const { sound } = await Audio.Sound.createAsync(
        { uri: payload.playback_url },
        { shouldPlay: false, isLooping: false }
      );

      if (!mountedRef.current) {
        await sound.unloadAsync();
        return;
      }

      standbyRef.current = { payload, sound };
      setStandby(payload);
    } catch {
      // Not fatal: we simply fetch on demand when this track ends.
    } finally {
      prefetchingRef.current = false;
    }
  }, []);

  // Stable bridge so `prefetchNext` can be used before its declaration.
  const prefetchNextRef = useRef(prefetchNext);
  prefetchNextRef.current = prefetchNext;

  const advance = useCallback(async () => {
    if (advancingRef.current) return;
    advancingRef.current = true;
    try {
      const next = standbyRef.current;
      if (next) {
        standbyRef.current = null;
        setStandby(null);

        const previous = soundRef.current;
        soundRef.current = next.sound;

        attachStatus(next.sound);
        setNowPlaying(next.payload);
        setPositionMs(0);
        setDurationMs(Math.max(0, (next.payload.song.duration_sec ?? 0) * 1000));
        setError(null);
        await next.sound.playAsync();

        if (previous) {
          try {
            previous.setOnPlaybackStatusUpdate(null);
            await previous.unloadAsync();
          } catch {
            // Ignore.
          }
        }
        void prefetchNextRef.current();
      } else {
        await loadNextNow();
      }
    } finally {
      advancingRef.current = false;
    }
  }, [attachStatus, loadNextNow]);

  useEffect(() => {
    endHandlerRef.current = () => {
      void advance();
    };
  }, [advance]);

  // ---------------------------------------------------------------------
  // Lifecycle
  // ---------------------------------------------------------------------

  useEffect(() => {
    mountedRef.current = true;

    const boot = async () => {
      try {
        await Audio.setAudioModeAsync({
          allowsRecordingIOS: false,
          playsInSilentModeIOS: true,
          staysActiveInBackground: false,
          shouldDuckAndroid: true,
          playThroughEarpieceAndroid: false,
        });
      } catch {
        // Audio mode is best effort; playback still works without it.
      }
      await loadNextNow();
    };

    void boot();

    return () => {
      mountedRef.current = false;
      const sound = soundRef.current;
      const standbyTrack = standbyRef.current;
      soundRef.current = null;
      standbyRef.current = null;
      sound?.unloadAsync().catch(() => {});
      standbyTrack?.sound.unloadAsync().catch(() => {});
    };
  }, [loadNextNow]);

  // ---------------------------------------------------------------------
  // Controls
  // ---------------------------------------------------------------------

  const togglePlay = useCallback(async () => {
    const sound = soundRef.current;
    if (!sound) return;
    try {
      const status = await sound.getStatusAsync();
      if (status.isLoaded && status.isPlaying) {
        await sound.pauseAsync();
      } else {
        await sound.playAsync();
      }
    } catch {
      // Ignore transient native errors.
    }
  }, []);

  const restartTrack = useCallback(async () => {
    const sound = soundRef.current;
    if (!sound) return;
    try {
      await sound.setPositionAsync(0);
      await sound.playAsync();
    } catch {
      // Ignore.
    }
  }, []);

  const seekTo = useCallback(async (fraction: number) => {
    const sound = soundRef.current;
    const total = durationMs;
    if (!sound || total <= 0) return;
    const clamped = Math.min(0.995, Math.max(0, fraction));
    try {
      await sound.setPositionAsync(Math.round(clamped * total));
      setPositionMs(clamped * total);
    } catch {
      // Ignore.
    }
  }, [durationMs]);

  const fractionFromTouch = (event: GestureResponderEvent): number => {
    const width = seekWidthRef.current;
    if (width <= 0) return 0;
    return Math.min(1, Math.max(0, event.nativeEvent.locationX / width));
  };

  // ---------------------------------------------------------------------
  // Helpers
  // ---------------------------------------------------------------------

  const formatTime = (ms: number): string => {
    if (!Number.isFinite(ms) || ms <= 0) return '0:00';
    const totalSeconds = Math.floor(ms / 1000);
    const minutes = Math.floor(totalSeconds / 60);
    const seconds = totalSeconds % 60;
    return `${minutes}:${seconds.toString().padStart(2, '0')}`;
  };

  const playedFraction =
    scrubFraction ?? (durationMs > 0 ? Math.min(1, positionMs / durationMs) : 0);

  // ---------------------------------------------------------------------
  // First-load screen
  // ---------------------------------------------------------------------

  if (loading && !nowPlaying) {
    return (
      <View style={styles.centered}>
        <View style={styles.pulse}>
          <MaterialIcons name="graphic-eq" size={34} color={colors.primary} />
        </View>
        <ActivityIndicator size="large" color={colors.primary} />
        <Text style={styles.loadingTitle}>Tuning in…</Text>
        <Text style={styles.loadingSubtitle}>
          Picking a random track from {playlist.total_songs} songs
        </Text>
      </View>
    );
  }

  if (error && !nowPlaying) {
    // The backend answers 503 with this hint when YouTube refuses the host's IP.
    const needsServerSetup = error.includes('YTDLP_COOKIES');
    return (
      <View style={styles.centered}>
        <MaterialIcons
          name={needsServerSetup ? 'cloud-off' : 'wifi-off'}
          size={44}
          color={colors.textTertiary}
        />
        <Text style={styles.loadingTitle}>
          {needsServerSetup ? 'Station needs one setup step' : 'Off air'}
        </Text>
        <Text style={styles.loadingSubtitle}>
          {needsServerSetup
            ? 'The playlist loaded fine, but YouTube will not stream audio to this server. Add a YouTube cookie to the backend as YTDLP_COOKIES and it will play. Running the backend on your own machine needs none of this.'
            : error}
        </Text>
        <Pressable
          style={({ pressed }) => [styles.retryButton, pressed && styles.pressed]}
          onPress={() => void loadNextNow()}
        >
          <Text style={styles.retryLabel}>Try again</Text>
        </Pressable>
        <Pressable onPress={() => navigation.goBack()} style={styles.linkButton}>
          <Text style={styles.linkLabel}>Change playlist</Text>
        </Pressable>
      </View>
    );
  }

  const art = nowPlaying?.song.thumbnail_url;

  return (
    <View style={styles.container}>
      {/* Blurred art wash */}
      {art ? (
        <Image
          source={{ uri: art }}
          style={StyleSheet.absoluteFill}
          contentFit="cover"
          cachePolicy="memory-disk"
          accessibilityIgnoresInvertColors
        />
      ) : null}
      <View style={styles.wash} />

      <View style={[styles.content, { paddingTop: insets.top + 12 }]}>
        {/* Top bar */}
        <View style={styles.topBar}>
          <Pressable
            hitSlop={12}
            onPress={() => navigation.goBack()}
            style={({ pressed }) => pressed && styles.pressed}
          >
            <MaterialIcons name="keyboard-arrow-down" size={28} color={colors.text} />
          </Pressable>

          <View style={styles.onAir}>
            <View style={styles.onAirDot} />
            <Text style={styles.onAirText}>ON AIR</Text>
          </View>

          <Pressable
            hitSlop={12}
            onPress={() => navigation.navigate('Queue')}
            style={({ pressed }) => pressed && styles.pressed}
          >
            <MaterialIcons name="queue-music" size={26} color={colors.text} />
          </Pressable>
        </View>

        {/* Artwork */}
        <View style={styles.artWrapper}>
          <View style={styles.artShadow}>
            {art ? (
              <Image
                source={{ uri: art }}
                style={styles.art}
                contentFit="cover"
                transition={250}
                cachePolicy="memory-disk"
                accessibilityIgnoresInvertColors
              />
            ) : (
              <View style={[styles.art, styles.artPlaceholder]}>
                <MaterialIcons name="album" size={72} color={colors.textTertiary} />
              </View>
            )}
          </View>
        </View>

        {/* Track info */}
        <View style={styles.trackInfo}>
          <Text style={styles.title} numberOfLines={2}>
            {nowPlaying?.song.title || 'Unknown title'}
          </Text>
          <Text style={styles.artist} numberOfLines={1}>
            {nowPlaying?.song.artist || 'Unknown artist'}
          </Text>
        </View>

        {error ? <Text style={styles.inlineError}>{error}</Text> : null}

        {/* Seek bar */}
        <View style={styles.seekSection}>
          <View
            style={styles.seekTrack}
            onLayout={(event: LayoutChangeEvent) => {
              seekWidthRef.current = event.nativeEvent.layout.width;
            }}
            onStartShouldSetResponder={() => true}
            onMoveShouldSetResponder={() => true}
            onResponderGrant={(event: GestureResponderEvent) =>
              setScrubFraction(fractionFromTouch(event))
            }
            onResponderMove={(event: GestureResponderEvent) =>
              setScrubFraction(fractionFromTouch(event))
            }
            onResponderRelease={(event: GestureResponderEvent) => {
              const fraction = fractionFromTouch(event);
              setScrubFraction(null);
              void seekTo(fraction);
            }}
            onResponderTerminate={() => setScrubFraction(null)}
          >
            <View style={styles.seekBackground}>
              <View style={[styles.seekFill, { width: `${playedFraction * 100}%` }]} />
              <View
                style={[styles.seekKnob, { left: `${playedFraction * 100}%` }]}
              />
            </View>
          </View>

          <View style={styles.timeRow}>
            <Text style={styles.time}>
              {formatTime(scrubFraction !== null ? scrubFraction * durationMs : positionMs)}
            </Text>
            <Text style={styles.time}>{formatTime(durationMs)}</Text>
          </View>
        </View>

        {/* Controls */}
        <View style={styles.controls}>
          <Pressable
            hitSlop={12}
            onPress={() => void restartTrack()}
            style={({ pressed }) => [styles.sideButton, pressed && styles.pressed]}
          >
            <MaterialIcons name="replay" size={30} color={colors.textSecondary} />
          </Pressable>

          <Pressable
            onPress={() => void togglePlay()}
            style={({ pressed }) => [styles.playButton, pressed && styles.playPressed]}
          >
            {isBuffering && isPlaying ? (
              <ActivityIndicator color={colors.text} />
            ) : (
              <MaterialIcons
                name={isPlaying ? 'pause' : 'play-arrow'}
                size={44}
                color={colors.text}
              />
            )}
          </Pressable>

          <Pressable
            hitSlop={12}
            onPress={() => void advance()}
            style={({ pressed }) => [styles.sideButton, pressed && styles.pressed]}
          >
            <MaterialIcons name="skip-next" size={36} color={colors.text} />
          </Pressable>
        </View>

        {/* Up next */}
        <View style={[styles.upNext, { marginBottom: insets.bottom + 8 }]}>
          <View style={styles.upNextLeft}>
            <Text style={styles.upNextLabel}>UP NEXT</Text>
            <Text style={styles.upNextTitle} numberOfLines={1}>
              {standby?.song.title ?? 'Lining up the next track…'}
            </Text>
          </View>
          <View style={styles.stationBadge}>
            <MaterialIcons name="shuffle" size={14} color={colors.primary} />
            <Text style={styles.stationBadgeText}>RANDOM</Text>
          </View>
        </View>
      </View>
    </View>
  );
};

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: colors.background,
  },
  wash: {
    ...StyleSheet.absoluteFillObject,
    backgroundColor: 'rgba(8, 8, 12, 0.9)',
  },
  content: {
    flex: 1,
    paddingHorizontal: 24,
    paddingBottom: 12,
  },
  centered: {
    flex: 1,
    backgroundColor: colors.background,
    alignItems: 'center',
    justifyContent: 'center',
    paddingHorizontal: 32,
  },
  pulse: {
    width: 72,
    height: 72,
    borderRadius: 36,
    backgroundColor: colors.primarySoft,
    alignItems: 'center',
    justifyContent: 'center',
    marginBottom: 24,
  },
  loadingTitle: {
    color: colors.text,
    fontSize: 20,
    fontWeight: '700',
    marginTop: 18,
  },
  loadingSubtitle: {
    color: colors.textSecondary,
    fontSize: 14,
    textAlign: 'center',
    marginTop: 8,
    lineHeight: 20,
  },
  errorText: {
    color: colors.error,
  },
  retryButton: {
    marginTop: 24,
    backgroundColor: colors.primary,
    paddingHorizontal: 28,
    paddingVertical: 13,
    borderRadius: borderRadius.full,
  },
  retryLabel: {
    color: colors.text,
    fontSize: 15,
    fontWeight: '700',
  },
  linkButton: {
    marginTop: 16,
    padding: 8,
  },
  linkLabel: {
    color: colors.textSecondary,
    fontSize: 14,
  },
  pressed: {
    opacity: 0.6,
  },
  topBar: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    marginBottom: 20,
  },
  onAir: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingHorizontal: 12,
    paddingVertical: 6,
    borderRadius: borderRadius.full,
    backgroundColor: 'rgba(244, 63, 94, 0.12)',
    borderWidth: 1,
    borderColor: 'rgba(244, 63, 94, 0.28)',
  },
  onAirDot: {
    width: 7,
    height: 7,
    borderRadius: 4,
    backgroundColor: colors.live,
    marginRight: 7,
  },
  onAirText: {
    color: colors.live,
    fontSize: 10,
    fontWeight: '800',
    letterSpacing: 1.4,
  },
  artWrapper: {
    alignItems: 'center',
    marginTop: 4,
  },
  artShadow: {
    borderRadius: borderRadius.xxl,
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 18 },
    shadowOpacity: 0.5,
    shadowRadius: 28,
    elevation: 18,
  },
  art: {
    width: ART_SIZE,
    height: ART_SIZE,
    borderRadius: borderRadius.xxl,
    backgroundColor: colors.surfaceVariant,
  },
  artPlaceholder: {
    alignItems: 'center',
    justifyContent: 'center',
  },
  trackInfo: {
    marginTop: 30,
  },
  title: {
    color: colors.text,
    fontSize: 23,
    fontWeight: '700',
    letterSpacing: -0.3,
    lineHeight: 29,
  },
  artist: {
    color: colors.textSecondary,
    fontSize: 15,
    marginTop: 6,
  },
  inlineError: {
    color: colors.error,
    fontSize: 13,
    marginTop: 12,
  },
  seekSection: {
    marginTop: 26,
  },
  seekTrack: {
    paddingVertical: 12,
    justifyContent: 'center',
  },
  seekBackground: {
    height: 4,
    borderRadius: 2,
    backgroundColor: 'rgba(255, 255, 255, 0.16)',
    justifyContent: 'center',
  },
  seekFill: {
    height: 4,
    borderRadius: 2,
    backgroundColor: colors.primary,
  },
  seekKnob: {
    position: 'absolute',
    top: -4,
    width: 12,
    height: 12,
    borderRadius: 6,
    backgroundColor: colors.text,
    marginLeft: -6,
  },
  timeRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    marginTop: 2,
  },
  time: {
    color: colors.textTertiary,
    fontSize: 12,
    fontVariant: ['tabular-nums'],
  },
  controls: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    marginTop: 22,
  },
  sideButton: {
    padding: 10,
  },
  playButton: {
    width: 78,
    height: 78,
    borderRadius: 39,
    backgroundColor: colors.primary,
    alignItems: 'center',
    justifyContent: 'center',
    marginHorizontal: 30,
    shadowColor: colors.primary,
    shadowOffset: { width: 0, height: 10 },
    shadowOpacity: 0.45,
    shadowRadius: 20,
    elevation: 14,
  },
  playPressed: {
    backgroundColor: colors.primaryVariant,
    transform: [{ scale: 0.96 }],
  },
  upNext: {
    marginTop: 'auto',
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: 'rgba(255, 255, 255, 0.05)',
    borderRadius: borderRadius.xl,
    borderWidth: 1,
    borderColor: colors.border,
    paddingHorizontal: 16,
    paddingVertical: 12,
  },
  upNextLeft: {
    flex: 1,
    marginRight: 12,
  },
  upNextLabel: {
    color: colors.textTertiary,
    fontSize: 9,
    fontWeight: '800',
    letterSpacing: 1.3,
  },
  upNextTitle: {
    color: colors.text,
    fontSize: 14,
    fontWeight: '600',
    marginTop: 4,
  },
  stationBadge: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingHorizontal: 10,
    paddingVertical: 6,
    borderRadius: borderRadius.full,
    backgroundColor: colors.primarySoft,
  },
  stationBadgeText: {
    color: colors.primary,
    fontSize: 9,
    fontWeight: '800',
    letterSpacing: 1,
    marginLeft: 4,
  },
});

export default PlayerScreen;
