import React, { useEffect, useState } from 'react';
import {
  ActivityIndicator,
  Keyboard,
  KeyboardAvoidingView,
  Platform,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  TextInput,
  View,
} from 'react-native';
import { MaterialIcons } from '@expo/vector-icons';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { StackNavigationProp } from '@react-navigation/stack';
import { apiService } from '../services/api';
import { LoadPlaylistResponse } from '../types';
import { colors, borderRadius } from '../styles/colors';

type RootStackParamList = {
  Playlist: undefined;
  Player: { playlist: LoadPlaylistResponse };
  Queue: undefined;
};

type PlaylistScreenNavigationProp = StackNavigationProp<RootStackParamList, 'Playlist'>;

interface Props {
  navigation: PlaylistScreenNavigationProp;
}

const LOADING_HINTS = [
  'Reading the playlist…',
  'Shuffling the deck…',
  'Tuning the antenna…',
];

const PlaylistScreen: React.FC<Props> = ({ navigation }) => {
  const insets = useSafeAreaInsets();
  const [playlistUrl, setPlaylistUrl] = useState('');
  const [loading, setLoading] = useState(false);
  const [hintIndex, setHintIndex] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const [station, setStation] = useState<LoadPlaylistResponse | null>(null);

  useEffect(() => {
    if (!loading) {
      setHintIndex(0);
      return;
    }
    const interval = setInterval(() => {
      setHintIndex((current) => (current + 1) % LOADING_HINTS.length);
    }, 2200);
    return () => clearInterval(interval);
  }, [loading]);

  const handleLoadPlaylist = async () => {
    const url = playlistUrl.trim();

    if (!url) {
      setError('Paste a YouTube playlist link to start your station.');
      return;
    }
    if (!/(youtube\.com|youtu\.be)/i.test(url)) {
      setError("That doesn't look like a YouTube playlist link.");
      return;
    }

    Keyboard.dismiss();
    setError(null);
    setLoading(true);

    try {
      const response = await apiService.loadPlaylist({ url, queue_size: 12 });

      if (!response.queue?.length) {
        throw new Error('That playlist has no playable songs.');
      }

      setStation(response);
      // Tune in right away — the first random track starts loading immediately.
      navigation.navigate('Player', { playlist: response });
    } catch (err) {
      setError(
        err instanceof Error ? err.message : 'Could not load that playlist.'
      );
    } finally {
      setLoading(false);
    }
  };

  return (
    <KeyboardAvoidingView
      style={styles.container}
      behavior={Platform.OS === 'ios' ? 'padding' : undefined}
    >
      <ScrollView
        contentContainerStyle={[
          styles.scrollContainer,
          { paddingTop: insets.top + 32, paddingBottom: insets.bottom + 24 },
        ]}
        keyboardShouldPersistTaps="handled"
        showsVerticalScrollIndicator={false}
      >
        {/* Brand */}
        <View style={styles.brand}>
          <View style={styles.logoMark}>
            <MaterialIcons name="graphic-eq" size={26} color={colors.text} />
          </View>
          <Text style={styles.wordmark}>
            VIBE<Text style={styles.wordmarkAccent}>FM</Text>
          </Text>
          <Text style={styles.tagline}>
            Your playlist, played like radio. Random order, zero decisions.
          </Text>
        </View>

        {/* Input card */}
        <View style={styles.card}>
          <Text style={styles.label}>PLAYLIST LINK</Text>

          <View style={styles.inputRow}>
            <MaterialIcons name="link" size={18} color={colors.textTertiary} />
            <TextInput
              style={styles.input}
              placeholder="https://youtube.com/playlist?list=…"
              placeholderTextColor={colors.textTertiary}
              value={playlistUrl}
              onChangeText={(text) => {
                setPlaylistUrl(text);
                if (error) setError(null);
              }}
              autoCapitalize="none"
              autoCorrect={false}
              keyboardType="url"
              returnKeyType="go"
              onSubmitEditing={() => void handleLoadPlaylist()}
              editable={!loading}
            />
            {playlistUrl.length > 0 && !loading ? (
              <Pressable hitSlop={10} onPress={() => setPlaylistUrl('')}>
                <MaterialIcons name="close" size={18} color={colors.textTertiary} />
              </Pressable>
            ) : null}
          </View>

          {error ? (
            <View style={styles.errorRow}>
              <MaterialIcons name="error-outline" size={15} color={colors.error} />
              <Text style={styles.errorText}>{error}</Text>
            </View>
          ) : null}

          <Pressable
            onPress={() => void handleLoadPlaylist()}
            disabled={loading}
            style={({ pressed }) => [
              styles.tuneButton,
              loading && styles.tuneButtonDisabled,
              pressed && !loading && styles.tuneButtonPressed,
            ]}
          >
            {loading ? (
              <>
                <ActivityIndicator color={colors.text} size="small" />
                <Text style={styles.tuneButtonText}>{LOADING_HINTS[hintIndex]}</Text>
              </>
            ) : (
              <>
                <MaterialIcons name="play-circle-filled" size={22} color={colors.text} />
                <Text style={styles.tuneButtonText}>Tune in</Text>
              </>
            )}
          </Pressable>

          <Text style={styles.cardHint}>
            Works with any public YouTube playlist. Audio only — nothing is
            downloaded.
          </Text>
        </View>

        {/* Current station */}
        {station ? (
          <Pressable
            style={({ pressed }) => [styles.stationCard, pressed && styles.pressed]}
            onPress={() => navigation.navigate('Player', { playlist: station })}
          >
            <View style={styles.stationDot} />
            <View style={styles.stationText}>
              <Text style={styles.stationLabel}>STATION LOADED</Text>
              <Text style={styles.stationMeta}>
                {station.total_songs} songs · {station.queue.length} in rotation
              </Text>
            </View>
            <MaterialIcons
              name="chevron-right"
              size={22}
              color={colors.textTertiary}
            />
          </Pressable>
        ) : null}

        {/* How it works */}
        <View style={styles.steps}>
          <Step
            index="1"
            title="Paste a playlist"
            body="Any public YouTube playlist link."
          />
          <Step
            index="2"
            title="We pick at random"
            body="Weighted shuffle favours tracks you haven't heard recently."
          />
          <Step
            index="3"
            title="It just plays"
            body="Next track is buffered while the current one finishes."
          />
        </View>
      </ScrollView>
    </KeyboardAvoidingView>
  );
};

const Step: React.FC<{ index: string; title: string; body: string }> = ({
  index,
  title,
  body,
}) => (
  <View style={styles.step}>
    <View style={styles.stepIndex}>
      <Text style={styles.stepIndexText}>{index}</Text>
    </View>
    <View style={styles.stepBody}>
      <Text style={styles.stepTitle}>{title}</Text>
      <Text style={styles.stepText}>{body}</Text>
    </View>
  </View>
);

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: colors.background,
  },
  scrollContainer: {
    paddingHorizontal: 24,
  },
  brand: {
    alignItems: 'center',
    marginBottom: 36,
  },
  logoMark: {
    width: 56,
    height: 56,
    borderRadius: 18,
    backgroundColor: colors.primarySoft,
    borderWidth: 1,
    borderColor: 'rgba(139, 92, 246, 0.3)',
    alignItems: 'center',
    justifyContent: 'center',
    marginBottom: 18,
  },
  wordmark: {
    color: colors.text,
    fontSize: 30,
    fontWeight: '800',
    letterSpacing: 2.5,
  },
  wordmarkAccent: {
    color: colors.primary,
  },
  tagline: {
    color: colors.textSecondary,
    fontSize: 14,
    lineHeight: 21,
    textAlign: 'center',
    marginTop: 10,
    maxWidth: 300,
  },
  card: {
    backgroundColor: colors.surface,
    borderRadius: borderRadius.xxl,
    borderWidth: 1,
    borderColor: colors.border,
    padding: 18,
  },
  label: {
    color: colors.textTertiary,
    fontSize: 10,
    fontWeight: '800',
    letterSpacing: 1.4,
    marginBottom: 10,
  },
  inputRow: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: colors.surfaceVariant,
    borderRadius: borderRadius.lg,
    borderWidth: 1,
    borderColor: colors.border,
    paddingHorizontal: 12,
    height: 50,
  },
  input: {
    flex: 1,
    color: colors.text,
    fontSize: 14,
    marginHorizontal: 10,
    paddingVertical: 0,
  },
  errorRow: {
    flexDirection: 'row',
    alignItems: 'flex-start',
    marginTop: 12,
  },
  errorText: {
    color: colors.error,
    fontSize: 13,
    lineHeight: 18,
    marginLeft: 6,
    flex: 1,
  },
  tuneButton: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: colors.primary,
    borderRadius: borderRadius.lg,
    height: 52,
    marginTop: 16,
  },
  tuneButtonDisabled: {
    backgroundColor: colors.surfaceElevated,
  },
  tuneButtonPressed: {
    backgroundColor: colors.primaryVariant,
  },
  tuneButtonText: {
    color: colors.text,
    fontSize: 16,
    fontWeight: '700',
    marginLeft: 8,
  },
  cardHint: {
    color: colors.textTertiary,
    fontSize: 12,
    lineHeight: 17,
    textAlign: 'center',
    marginTop: 14,
  },
  stationCard: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: colors.surface,
    borderRadius: borderRadius.xl,
    borderWidth: 1,
    borderColor: colors.border,
    padding: 16,
    marginTop: 16,
  },
  stationDot: {
    width: 8,
    height: 8,
    borderRadius: 4,
    backgroundColor: colors.live,
    marginRight: 12,
  },
  stationText: {
    flex: 1,
  },
  stationLabel: {
    color: colors.textTertiary,
    fontSize: 9,
    fontWeight: '800',
    letterSpacing: 1.3,
  },
  stationMeta: {
    color: colors.text,
    fontSize: 14,
    fontWeight: '600',
    marginTop: 4,
  },
  steps: {
    marginTop: 32,
  },
  step: {
    flexDirection: 'row',
    alignItems: 'flex-start',
    marginBottom: 18,
  },
  stepIndex: {
    width: 26,
    height: 26,
    borderRadius: 13,
    backgroundColor: colors.surfaceVariant,
    alignItems: 'center',
    justifyContent: 'center',
    marginRight: 14,
    marginTop: 1,
  },
  stepIndexText: {
    color: colors.textSecondary,
    fontSize: 11,
    fontWeight: '800',
  },
  stepBody: {
    flex: 1,
  },
  stepTitle: {
    color: colors.text,
    fontSize: 14,
    fontWeight: '700',
  },
  stepText: {
    color: colors.textTertiary,
    fontSize: 12.5,
    lineHeight: 18,
    marginTop: 3,
  },
  pressed: {
    opacity: 0.7,
  },
});

export default PlaylistScreen;
