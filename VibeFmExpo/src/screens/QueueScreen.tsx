import React, { useCallback, useEffect, useState } from 'react';
import {
  ActivityIndicator,
  FlatList,
  Pressable,
  RefreshControl,
  StyleSheet,
  Text,
  View,
} from 'react-native';
import { Image } from 'expo-image';
import { MaterialIcons } from '@expo/vector-icons';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { StackNavigationProp } from '@react-navigation/stack';
import { apiService } from '../services/api';
import { Song } from '../types';
import { colors, borderRadius } from '../styles/colors';

type RootStackParamList = {
  Playlist: undefined;
  Player: { playlist: any };
  Queue: undefined;
};

type QueueScreenNavigationProp = StackNavigationProp<RootStackParamList, 'Queue'>;

interface Props {
  navigation: QueueScreenNavigationProp;
}

const QueueScreen: React.FC<Props> = ({ navigation }) => {
  const insets = useSafeAreaInsets();
  const [queue, setQueue] = useState<Song[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const loadQueue = useCallback(async () => {
    try {
      const queueData = await apiService.getQueue();
      setQueue(queueData);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not load the queue.');
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, []);

  useEffect(() => {
    void loadQueue();
  }, [loadQueue]);

  const formatDuration = (seconds: number): string => {
    if (!seconds) return '--:--';
    const mins = Math.floor(seconds / 60);
    const secs = Math.floor(seconds % 60);
    return `${mins}:${secs.toString().padStart(2, '0')}`;
  };

  const renderSong = ({ item, index }: { item: Song; index: number }) => (
    <View style={styles.row}>
      <Text style={styles.index}>{String(index + 1).padStart(2, '0')}</Text>

      {item.thumbnail_url ? (
        <Image
          source={{ uri: item.thumbnail_url }}
          style={styles.thumbnail}
          contentFit="cover"
          cachePolicy="memory-disk"
          transition={150}
          accessibilityIgnoresInvertColors
        />
      ) : (
        <View style={[styles.thumbnail, styles.thumbnailPlaceholder]}>
          <MaterialIcons name="music-note" size={18} color={colors.textTertiary} />
        </View>
      )}

      <View style={styles.rowText}>
        <Text style={styles.rowTitle} numberOfLines={1}>
          {item.title}
        </Text>
        <Text style={styles.rowArtist} numberOfLines={1}>
          {item.artist}
          {item.play_count > 0 ? `  ·  played ${item.play_count}×` : ''}
        </Text>
      </View>

      <Text style={styles.duration}>{formatDuration(item.duration_sec)}</Text>
    </View>
  );

  return (
    <View style={styles.container}>
      <View style={[styles.topBar, { paddingTop: insets.top + 10 }]}>
        <Pressable hitSlop={12} onPress={() => navigation.goBack()}>
          <MaterialIcons name="keyboard-arrow-down" size={28} color={colors.text} />
        </Pressable>

        <View style={styles.topBarText}>
          <Text style={styles.topBarTitle}>Up next</Text>
          <Text style={styles.topBarSubtitle}>
            {queue.length ? `${queue.length} songs in rotation` : 'Nothing queued'}
          </Text>
        </View>

        <Pressable hitSlop={12} onPress={() => void loadQueue()}>
          <MaterialIcons name="refresh" size={22} color={colors.textSecondary} />
        </Pressable>
      </View>

      {loading ? (
        <View style={styles.centered}>
          <ActivityIndicator size="large" color={colors.primary} />
          <Text style={styles.centeredText}>Loading queue…</Text>
        </View>
      ) : queue.length === 0 ? (
        <View style={styles.centered}>
          <View style={styles.emptyIcon}>
            <MaterialIcons name="queue-music" size={32} color={colors.textTertiary} />
          </View>
          <Text style={styles.emptyTitle}>
            {error ? 'Off air' : 'No songs queued'}
          </Text>
          <Text style={styles.centeredText}>
            {error ?? 'Load a playlist and the shuffle will fill this list.'}
          </Text>
          <Pressable
            style={({ pressed }) => [styles.cta, pressed && styles.pressed]}
            onPress={() => navigation.navigate('Playlist')}
          >
            <Text style={styles.ctaText}>Choose a playlist</Text>
          </Pressable>
        </View>
      ) : (
        <FlatList
          data={queue}
          keyExtractor={(item, index) => `${item.video_id}-${index}`}
          renderItem={renderSong}
          ItemSeparatorComponent={() => <View style={styles.separator} />}
          contentContainerStyle={{ paddingBottom: insets.bottom + 24 }}
          showsVerticalScrollIndicator={false}
          refreshControl={
            <RefreshControl
              refreshing={refreshing}
              onRefresh={() => {
                setRefreshing(true);
                void loadQueue();
              }}
              tintColor={colors.primary}
              colors={[colors.primary]}
              progressBackgroundColor={colors.surface}
            />
          }
        />
      )}
    </View>
  );
};

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: colors.background,
  },
  topBar: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingHorizontal: 20,
    paddingBottom: 16,
  },
  topBarText: {
    flex: 1,
    alignItems: 'center',
  },
  topBarTitle: {
    color: colors.text,
    fontSize: 16,
    fontWeight: '700',
  },
  topBarSubtitle: {
    color: colors.textTertiary,
    fontSize: 11,
    marginTop: 2,
  },
  row: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingHorizontal: 20,
    paddingVertical: 10,
  },
  index: {
    color: colors.textTertiary,
    fontSize: 12,
    fontVariant: ['tabular-nums'],
    width: 26,
  },
  thumbnail: {
    width: 46,
    height: 46,
    borderRadius: borderRadius.md,
    backgroundColor: colors.surfaceVariant,
  },
  thumbnailPlaceholder: {
    alignItems: 'center',
    justifyContent: 'center',
  },
  rowText: {
    flex: 1,
    marginLeft: 14,
    marginRight: 12,
  },
  rowTitle: {
    color: colors.text,
    fontSize: 14.5,
    fontWeight: '600',
  },
  rowArtist: {
    color: colors.textTertiary,
    fontSize: 12,
    marginTop: 3,
  },
  duration: {
    color: colors.textTertiary,
    fontSize: 12,
    fontVariant: ['tabular-nums'],
  },
  separator: {
    height: 1,
    backgroundColor: colors.border,
    marginLeft: 106,
    marginRight: 20,
  },
  centered: {
    flex: 1,
    alignItems: 'center',
    justifyContent: 'center',
    paddingHorizontal: 40,
    paddingBottom: 60,
  },
  centeredText: {
    color: colors.textSecondary,
    fontSize: 13.5,
    lineHeight: 20,
    textAlign: 'center',
    marginTop: 8,
  },
  emptyIcon: {
    width: 64,
    height: 64,
    borderRadius: 32,
    backgroundColor: colors.surface,
    alignItems: 'center',
    justifyContent: 'center',
    marginBottom: 18,
  },
  emptyTitle: {
    color: colors.text,
    fontSize: 17,
    fontWeight: '700',
  },
  cta: {
    marginTop: 22,
    backgroundColor: colors.primary,
    paddingHorizontal: 24,
    paddingVertical: 12,
    borderRadius: borderRadius.full,
  },
  ctaText: {
    color: colors.text,
    fontSize: 14,
    fontWeight: '700',
  },
  pressed: {
    opacity: 0.7,
  },
});

export default QueueScreen;
