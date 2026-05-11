import React, { useState, useEffect } from 'react';
import {
  View,
  Text,
  FlatList,
  TouchableOpacity,
  StyleSheet,
  Image,
  ActivityIndicator,
  Alert,
  RefreshControl,
} from 'react-native';
import { apiService } from '../services/api';
import { Song } from '../types';
import { StackNavigationProp } from '@react-navigation/stack';
import { MaterialIcons } from '@expo/vector-icons';

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
  const [queue, setQueue] = useState<Song[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);

  useEffect(() => {
    loadQueue();
  }, []);

  const loadQueue = async () => {
    try {
      const queueData = await apiService.getQueue();
      setQueue(queueData);
    } catch (error) {
      Alert.alert('Error', error instanceof Error ? error.message : 'Failed to load queue');
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  };

  const handleRefresh = () => {
    setRefreshing(true);
    loadQueue();
  };

  const handleSongPress = (song: Song) => {
    // Navigate to player with specific song
    // In a real implementation, you'd pass the song and queue position
    Alert.alert('Song Selected', `Would play: ${song.title}`);
  };

  const formatDuration = (seconds: number): string => {
    const mins = Math.floor(seconds / 60);
    const secs = Math.floor(seconds % 60);
    return `${mins}:${secs.toString().padStart(2, '0')}`;
  };

  const renderSongItem = ({ item, index }: { item: Song; index: number }) => (
    <TouchableOpacity 
      style={styles.songItem}
      onPress={() => handleSongPress(item)}
    >
      <View style={styles.songNumber}>
        <Text style={styles.songNumberText}>{index + 1}</Text>
      </View>
      
      {item.thumbnail_url ? (
        <Image source={{ uri: item.thumbnail_url }} style={styles.thumbnail} />
      ) : (
        <View style={[styles.thumbnail, styles.placeholderThumbnail]}>
          <MaterialIcons name="music-note" size={20} color="#4a4a4a" />
        </View>
      )}
      
      <View style={styles.songInfo}>
        <Text style={styles.songTitle} numberOfLines={1}>
          {item.title}
        </Text>
        <Text style={styles.artistName} numberOfLines={1}>
          {item.artist}
        </Text>
      </View>
      
      <View style={styles.songMeta}>
        <Text style={styles.duration}>
          {formatDuration(item.duration_sec)}
        </Text>
        {item.play_count > 0 && (
          <View style={styles.playCount}>
            <MaterialIcons name="play-arrow" size={12} color="#6366f1" />
            <Text style={styles.playCountText}>{item.play_count}</Text>
          </View>
        )}
      </View>
    </TouchableOpacity>
  );

  const renderSeparator = () => <View style={styles.separator} />;

  const renderHeader = () => (
    <View style={styles.header}>
      <Text style={styles.headerTitle}>Queue</Text>
      <Text style={styles.queueInfo}>
        {queue.length} songs in queue
      </Text>
    </View>
  );

  if (loading) {
    return (
      <View style={styles.loadingContainer}>
        <ActivityIndicator size="large" color="#6366f1" />
        <Text style={styles.loadingText}>Loading queue...</Text>
      </View>
    );
  }

  return (
    <View style={styles.container}>
      <View style={styles.topBar}>
        <TouchableOpacity onPress={() => navigation.goBack()}>
          <MaterialIcons name="arrow-back" size={24} color="#ffffff" />
        </TouchableOpacity>
        <Text style={styles.topBarTitle}>Queue</Text>
        <TouchableOpacity onPress={handleRefresh}>
          <MaterialIcons name="refresh" size={24} color="#ffffff" />
        </TouchableOpacity>
      </View>

      <FlatList
        data={queue}
        renderItem={renderSongItem}
        keyExtractor={(item) => item.video_id}
        ItemSeparatorComponent={renderSeparator}
        ListHeaderComponent={renderHeader}
        refreshControl={
          <RefreshControl
            refreshing={refreshing}
            onRefresh={handleRefresh}
            tintColor="#6366f1"
            colors={["#6366f1"]}
          />
        }
        contentContainerStyle={styles.listContainer}
        showsVerticalScrollIndicator={false}
      />

      {queue.length === 0 && (
        <View style={styles.emptyState}>
          <MaterialIcons name="queue-music" size={64} color="#4a4a4a" />
          <Text style={styles.emptyTitle}>No songs in queue</Text>
          <Text style={styles.emptySubtitle}>
            Load a playlist to start building your queue
          </Text>
          <TouchableOpacity
            style={styles.loadPlaylistButton}
            onPress={() => navigation.navigate('Playlist')}
          >
            <Text style={styles.loadPlaylistButtonText}>Load Playlist</Text>
          </TouchableOpacity>
        </View>
      )}
    </View>
  );
};

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: '#1a1a1a',
  },
  topBar: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    paddingHorizontal: '5%',
    paddingVertical: '4%',
    backgroundColor: '#2a2a2a',
  },
  topBarTitle: {
    fontSize: 18,
    fontWeight: '600',
    color: '#ffffff',
  },
  listContainer: {
    flexGrow: 1,
  },
  songItem: {
    flexDirection: 'row',
    alignItems: 'center',
    padding: '4%',
    backgroundColor: '#1a1a1a',
  },
  songNumber: {
    width: 30,
    height: 30,
    borderRadius: 15,
    backgroundColor: '#2a2a2a',
    justifyContent: 'center',
    alignItems: 'center',
    marginRight: '4%',
  },
  songNumberText: {
    color: '#ffffff',
    fontSize: 14,
    fontWeight: '600',
  },
  thumbnail: {
    width: 50,
    height: 50,
    borderRadius: 8,
    marginRight: '4%',
  },
  placeholderThumbnail: {
    backgroundColor: '#2a2a2a',
    justifyContent: 'center',
    alignItems: 'center',
  },
  songInfo: {
    flex: 1,
  },
  songTitle: {
    fontSize: 16,
    fontWeight: '600',
    color: '#ffffff',
    marginBottom: 4,
  },
  artistName: {
    fontSize: 14,
    color: '#b0b0b0',
  },
  songMeta: {
    flexDirection: 'row',
    alignItems: 'center',
  },
  duration: {
    fontSize: 14,
    color: '#808080',
    marginRight: 12,
  },
  playCount: {
    flexDirection: 'row',
    alignItems: 'center',
  },
  playCountText: {
    fontSize: 12,
    color: '#6366f1',
    marginLeft: 4,
  },
  separator: {
    height: 1,
    backgroundColor: '#2a2a2a',
    marginHorizontal: '4%',
  },
  emptyState: {
    flex: 1,
    justifyContent: 'center',
    alignItems: 'center',
    paddingHorizontal: '20%',
  },
  emptyTitle: {
    fontSize: 20,
    fontWeight: 'bold',
    color: '#ffffff',
    marginTop: 16,
    marginBottom: 8,
  },
  emptySubtitle: {
    fontSize: 16,
    color: '#b0b0b0',
    textAlign: 'center',
    marginBottom: 24,
  },
  loadPlaylistButton: {
    backgroundColor: '#6366f1',
    paddingHorizontal: 24,
    paddingVertical: 12,
    borderRadius: 8,
  },
  loadPlaylistButtonText: {
    color: '#ffffff',
    fontSize: 16,
    fontWeight: '600',
  },
  // Missing styles that are referenced in JSX
  header: {
    paddingHorizontal: '5%',
    paddingVertical: '4%',
    backgroundColor: '#2a2a2a',
  },
  headerTitle: {
    fontSize: 20,
    fontWeight: 'bold',
    color: '#ffffff',
    marginBottom: 8,
  },
  queueInfo: {
    fontSize: 16,
    color: '#b0b0b0',
  },
  loadingContainer: {
    flex: 1,
    backgroundColor: '#1a1a1a',
    justifyContent: 'center',
    alignItems: 'center',
  },
  loadingText: {
    color: '#ffffff',
    fontSize: 16,
    marginTop: 16,
  },
});

export default QueueScreen;
