import React, { useState, useEffect, useRef } from 'react';
import {
  View,
  Text,
  TouchableOpacity,
  StyleSheet,
  Dimensions,
  ActivityIndicator,
  Alert,
  Image,
} from 'react-native';
import { StackNavigationProp } from '@react-navigation/stack';
import { MaterialIcons } from '@expo/vector-icons';
import { Audio } from 'expo-av';
import { apiService } from '../services/api';
import { LoadPlaylistResponse, NextSongResponse } from '../types';
import { responsiveFontSize, isTablet, getOrientation } from '../utils/responsive';

type RootStackParamList = {
  Playlist: undefined;
  Player: { playlist: LoadPlaylistResponse };
  Queue: undefined;
};

type PlayerScreenNavigationProp = StackNavigationProp<RootStackParamList, 'Player'>;

interface Props {
  route: {
    params: {
      playlist: LoadPlaylistResponse;
    };
  };
  navigation: PlayerScreenNavigationProp;
}

const { width, height } = Dimensions.get('window');

const PlayerScreen: React.FC<Props> = ({ route, navigation }) => {
  const [screenDimensions, setScreenDimensions] = useState(Dimensions.get('window'));
  
  useEffect(() => {
    const onChange = (result: any) => {
      setScreenDimensions(result.window);
    };
    
    const subscription = Dimensions.addEventListener('change', onChange);
    
    return () => subscription?.remove();
  }, []);

  const { playlist } = route.params;
  
  const [currentSong, setCurrentSong] = useState<NextSongResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [isPlaying, setIsPlaying] = useState(false);
  const [position, setPosition] = useState(0);
  const [duration, setDuration] = useState(0);
  const sound = useRef<Audio.Sound | null>(null);
  const [isAudioLoaded, setIsAudioLoaded] = useState(false);

  useEffect(() => {
    loadNextSong();
    
    // Cleanup function
    return () => {
      if (sound.current) {
        sound.current.unloadAsync();
      }
    };
  }, []);

  const loadAndPlayAudio = async (streamUrl: string) => {
    try {
      // Unload previous sound if exists
      if (sound.current) {
        await sound.current.unloadAsync();
      }

      // Load new sound
      const { sound: newSound } = await Audio.Sound.createAsync(
        { uri: streamUrl },
        {
          shouldPlay: false,
          isLooping: false,
        }
      );

      sound.current = newSound;
      
      // Set up status update listener
      newSound.setOnPlaybackStatusUpdate((status) => {
        if (status.isLoaded) {
          setDuration(status.durationMillis ? status.durationMillis / 1000 : 0);
          setPosition(status.positionMillis ? status.positionMillis / 1000 : 0);
          setIsPlaying(status.isPlaying || false);
          
          // Auto-load next song when current song ends
          if (status.didJustFinish) {
            loadNextSong();
          }
        }
      });

      setIsAudioLoaded(true);
    } catch (error) {
      console.error('Error loading audio:', error);
      Alert.alert('Error', 'Failed to load audio');
    }
  };

  const loadNextSong = async () => {
    setLoading(true);
    setIsAudioLoaded(false);
    
    try {
      const nextSong = await apiService.getNextSong();
      
      if (!nextSong) {
        throw new Error('No song returned from API');
      }
      
      setCurrentSong(nextSong);
      setDuration(nextSong.song.duration_sec || 0);
      setPosition(0);
      setIsPlaying(false);

      // Load the audio
      await loadAndPlayAudio(nextSong.stream.stream_url);
    } catch (error) {
      console.error('Error in loadNextSong:', error);
      Alert.alert('Error', error instanceof Error ? error.message : 'Failed to load next song');
    } finally {
      setLoading(false);
    }
  };

  const handlePlayPause = async () => {
    if (!sound.current || !isAudioLoaded) return;

    try {
      if (isPlaying) {
        await sound.current.pauseAsync();
      } else {
        await sound.current.playAsync();
      }
    } catch (error) {
      console.error('Error toggling playback:', error);
      Alert.alert('Error', 'Failed to control playback');
    }
  };

  const handleNext = () => {
    loadNextSong();
  };

  const handlePrevious = async () => {
    if (!sound.current || !isAudioLoaded) return;

    try {
      await sound.current.setPositionAsync(0);
      if (!isPlaying) {
        await sound.current.playAsync();
      }
    } catch (error) {
      console.error('Error restarting song:', error);
    }
  };

  const formatTime = (seconds: number): string => {
    const mins = Math.floor(seconds / 60);
    const secs = Math.floor(seconds % 60);
    return `${mins}:${secs.toString().padStart(2, '0')}`;
  };

  const handleViewQueue = () => {
    navigation.navigate('Queue');
  };

  if (loading && !currentSong) {
    return (
      <View style={styles.loadingContainer}>
        <ActivityIndicator size="large" color="#6366f1" />
        <Text style={styles.loadingText}>Loading next song...</Text>
      </View>
    );
  }

  return (
    <View style={styles.container}>
      {/* Header */}
      <View style={styles.header}>
        <TouchableOpacity onPress={() => navigation.goBack()}>
          <MaterialIcons name="arrow-back" size={24} color="#ffffff" />
        </TouchableOpacity>
        <Text style={styles.headerTitle}>Now Playing</Text>
        <TouchableOpacity onPress={handleViewQueue}>
          <MaterialIcons name="queue-music" size={24} color="#ffffff" />
        </TouchableOpacity>
      </View>

      {/* Album Art */}
      <View style={styles.albumArtContainer}>
        {currentSong?.song.thumbnail_url ? (
          <Image
            source={{ uri: currentSong.song.thumbnail_url }}
            style={styles.albumArt}
            resizeMode="cover"
          />
        ) : (
          <View style={[styles.albumArt, styles.placeholderArt]}>
            <MaterialIcons name="album" size={80} color="#4a4a4a" />
          </View>
        )}
      </View>

      {/* Song Info */}
      <View style={styles.songInfo}>
        <Text style={styles.songTitle} numberOfLines={2}>
          {currentSong?.song.title || 'Unknown Title'}
        </Text>
        <Text style={styles.artistName} numberOfLines={1}>
          {currentSong?.song.artist || 'Unknown Artist'}
        </Text>
      </View>

      {/* Progress Bar */}
      <View style={styles.progressContainer}>
        <Text style={styles.timeText}>{formatTime(position)}</Text>
        <View style={styles.progressBar}>
          <View 
            style={[
              styles.progressFill, 
              { width: `${duration > 0 ? (position / duration) * 100 : 0}%` }
            ]} 
          />
        </View>
        <Text style={styles.timeText}>{formatTime(duration)}</Text>
      </View>

      {/* Controls */}
      <View style={styles.controls}>
        <TouchableOpacity style={styles.controlButton} onPress={handlePrevious}>
          <MaterialIcons name="skip-previous" size={32} color="#ffffff" />
        </TouchableOpacity>

        <TouchableOpacity 
          style={[styles.playButton, (loading || !isAudioLoaded) && styles.playButtonDisabled]} 
          onPress={handlePlayPause}
          disabled={loading || !isAudioLoaded}
        >
          {loading ? (
            <ActivityIndicator size="large" color="#ffffff" />
          ) : (
            <MaterialIcons 
              name={isPlaying ? "pause" : "play-arrow"} 
              size={40} 
              color="#ffffff" 
            />
          )}
        </TouchableOpacity>

        <TouchableOpacity style={styles.controlButton} onPress={handleNext}>
          <MaterialIcons name="skip-next" size={32} color="#ffffff" />
        </TouchableOpacity>
      </View>

      {/* Additional Controls */}
      <View style={styles.additionalControls}>
        <TouchableOpacity style={styles.extraButton}>
          <MaterialIcons name="shuffle" size={24} color="#6366f1" />
        </TouchableOpacity>
        <TouchableOpacity style={styles.extraButton}>
          <MaterialIcons name="repeat" size={24} color="#4a4a4a" />
        </TouchableOpacity>
        <TouchableOpacity style={styles.extraButton}>
          <MaterialIcons name="favorite-border" size={24} color="#4a4a4a" />
        </TouchableOpacity>
      </View>

      {/* Debug Info - Stream URL */}
      {currentSong && (
        <View style={styles.debugContainer}>
          <Text style={styles.debugTitle}>Stream URL Debug:</Text>
          <Text style={styles.debugUrl} numberOfLines={3}>
            {currentSong.stream.stream_url}
          </Text>
          <Text style={styles.debugProxy}>
            Proxy: {apiService.getAudioUrl(currentSong.song.video_id)}
          </Text>
        </View>
      )}

      {/* Footer Info */}
      {currentSong && (
        <View style={styles.footer}>
          <Text style={styles.footerText}>
            From playlist: {playlist.total_songs} songs loaded
          </Text>
        </View>
      )}
    </View>
  );
};

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: '#1a1a1a',
    padding: '5%',
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
  header: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: '8%',
  },
  headerTitle: {
    fontSize: responsiveFontSize(18),
    fontWeight: '600',
    color: '#ffffff',
  },
  albumArtContainer: {
    alignItems: 'center',
    marginBottom: '8%',
  },
  albumArt: {
    width: isTablet() ? '50%' : '70%',
    height: undefined,
    aspectRatio: 1,
    borderRadius: 12,
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 4 },
    shadowOpacity: 0.3,
    shadowRadius: 8,
    elevation: 8,
  },
  placeholderArt: {
    backgroundColor: '#2a2a2a',
    justifyContent: 'center',
    alignItems: 'center',
  },
  songInfo: {
    alignItems: 'center',
    marginBottom: '8%',
    paddingHorizontal: '5%',
  },
  songTitle: {
    fontSize: responsiveFontSize(24),
    fontWeight: 'bold',
    color: '#ffffff',
    textAlign: 'center',
    marginBottom: 8,
  },
  artistName: {
    fontSize: responsiveFontSize(16),
    color: '#b0b0b0',
    textAlign: 'center',
  },
  progressContainer: {
    flexDirection: 'row',
    alignItems: 'center',
    marginBottom: '8%',
  },
  timeText: {
    color: '#b0b0b0',
    fontSize: responsiveFontSize(14),
    width: 40,
  },
  progressBar: {
    flex: 1,
    height: 4,
    backgroundColor: '#3a3a3a',
    borderRadius: 2,
    marginHorizontal: 12,
  },
  progressFill: {
    height: '100%',
    backgroundColor: '#6366f1',
    borderRadius: 2,
  },
  controls: {
    flexDirection: 'row',
    justifyContent: 'center',
    alignItems: 'center',
    marginBottom: '10%',
  },
  controlButton: {
    padding: '4%',
  },
  playButton: {
    backgroundColor: '#6366f1',
    width: isTablet() ? 100 : 80,
    height: isTablet() ? 100 : 80,
    borderRadius: isTablet() ? 50 : 40,
    justifyContent: 'center',
    alignItems: 'center',
    marginHorizontal: '5%',
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 4 },
    shadowOpacity: 0.3,
    shadowRadius: 8,
    elevation: 8,
  },
  playButtonDisabled: {
    backgroundColor: '#4a4a4a',
  },
  additionalControls: {
    flexDirection: 'row',
    justifyContent: 'space-around',
    alignItems: 'center',
    marginBottom: '8%',
  },
  extraButton: {
    padding: '3%',
  },
  footer: {
    alignItems: 'center',
    marginTop: 'auto',
  },
  footerText: {
    color: '#808080',
    fontSize: responsiveFontSize(14),
  },
  debugContainer: {
    backgroundColor: '#2a2a2a',
    padding: '3%',
    borderRadius: 8,
    marginVertical: '2%',
  },
  debugTitle: {
    color: '#6366f1',
    fontSize: responsiveFontSize(12),
    fontWeight: '600',
    marginBottom: 4,
  },
  debugUrl: {
    color: '#ffffff',
    fontSize: responsiveFontSize(10),
    fontFamily: 'monospace',
    marginBottom: 4,
  },
  debugProxy: {
    color: '#808080',
    fontSize: responsiveFontSize(10),
    fontFamily: 'monospace',
  },
});

export default PlayerScreen;
