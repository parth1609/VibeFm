import React, { useState } from 'react';
import {
  View,
  Text,
  TextInput,
  TouchableOpacity,
  StyleSheet,
  Alert,
  ActivityIndicator,
  KeyboardAvoidingView,
  Platform,
  ScrollView,
} from 'react-native';
import { apiService } from '../services/api';
import { LoadPlaylistResponse } from '../types';
import { StackNavigationProp } from '@react-navigation/stack';

type RootStackParamList = {
  Playlist: undefined;
  Player: { playlist: LoadPlaylistResponse };
  Queue: undefined;
};

type PlaylistScreenNavigationProp = StackNavigationProp<RootStackParamList, 'Playlist'>;

interface Props {
  navigation: PlaylistScreenNavigationProp;
}

const PlaylistScreen: React.FC<Props> = ({ navigation }) => {
  const [playlistUrl, setPlaylistUrl] = useState('');
  const [loading, setLoading] = useState(false);
  const [playlistData, setPlaylistData] = useState<LoadPlaylistResponse | null>(null);

  const handleLoadPlaylist = async () => {
    if (!playlistUrl.trim()) {
      Alert.alert('Error', 'Please enter a YouTube playlist URL');
      return;
    }

    setLoading(true);
    try {
      const response = await apiService.loadPlaylist({
        url: playlistUrl.trim(),
        queue_size: 10,
      });
      
      setPlaylistData(response);
      Alert.alert(
        'Success',
        `Loaded ${response.total_songs} songs from playlist!`,
        [
          {
            text: 'View Queue',
            onPress: () => navigation.navigate('Queue'),
          },
          {
            text: 'Start Playing',
            onPress: () => navigation.navigate('Player', { playlist: response }),
          },
          {
            text: 'OK',
            style: 'cancel',
          },
        ]
      );
    } catch (error) {
      Alert.alert('Error', error instanceof Error ? error.message : 'Failed to load playlist');
    } finally {
      setLoading(false);
    }
  };

  const handleStartPlaying = () => {
    if (playlistData) {
      navigation.navigate('Player', { playlist: playlistData });
    }
  };

  const handleViewQueue = () => {
    navigation.navigate('Queue');
  };

  return (
    <KeyboardAvoidingView 
      style={styles.container} 
      behavior={Platform.OS === 'ios' ? 'padding' : 'height'}
    >
      <ScrollView contentContainerStyle={styles.scrollContainer}>
        <View style={styles.header}>
          <Text style={styles.title}>VibeFM</Text>
          <Text style={styles.subtitle}>AI Personal Radio Station</Text>
        </View>

        <View style={styles.inputSection}>
          <Text style={styles.label}>YouTube Playlist URL</Text>
          <TextInput
            style={styles.input}
            placeholder="https://www.youtube.com/playlist?list=..."
            value={playlistUrl}
            onChangeText={setPlaylistUrl}
            multiline={true}
            numberOfLines={3}
            autoCapitalize="none"
            autoCorrect={false}
          />
        </View>

        <TouchableOpacity
          style={[styles.button, loading && styles.buttonDisabled]}
          onPress={handleLoadPlaylist}
          disabled={loading}
        >
          {loading ? (
            <ActivityIndicator color="#ffffff" size="small" />
          ) : (
            <Text style={styles.buttonText}>Load Playlist</Text>
          )}
        </TouchableOpacity>

        {playlistData && (
          <View style={styles.playlistInfo}>
            <Text style={styles.infoTitle}>Playlist Loaded!</Text>
            <Text style={styles.infoText}>
              Total Songs: {playlistData.total_songs}
            </Text>
            <Text style={styles.infoText}>
              Queue Size: {playlistData.queue.length}
            </Text>
            
            <View style={styles.actionButtons}>
              <TouchableOpacity
                style={[styles.secondaryButton, styles.actionButton]}
                onPress={handleViewQueue}
              >
                <Text style={styles.secondaryButtonText}>View Queue</Text>
              </TouchableOpacity>
              
              <TouchableOpacity
                style={[styles.primaryButton, styles.actionButton]}
                onPress={handleStartPlaying}
              >
                <Text style={styles.primaryButtonText}>Start Playing</Text>
              </TouchableOpacity>
            </View>
          </View>
        )}

        <View style={styles.footer}>
          <Text style={styles.footerText}>
            Enter a YouTube playlist URL to start your personalized radio experience
          </Text>
        </View>
      </ScrollView>
    </KeyboardAvoidingView>
  );
};

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: '#1a1a1a',
    padding: '5%',
  },
  scrollContainer: {
    flexGrow: 1,
  },
  header: {
    alignItems: 'center',
    marginBottom: '10%',
  },
  title: {
    fontSize: 32,
    fontWeight: 'bold',
    color: '#ffffff',
    marginBottom: 8,
  },
  subtitle: {
    fontSize: 16,
    color: '#b0b0b0',
    textAlign: 'center',
  },
  inputSection: {
    marginBottom: '8%',
  },
  inputContainer: {
    marginBottom: '8%',
  },
  label: {
    fontSize: 16,
    fontWeight: '600',
    color: '#ffffff',
    marginBottom: 12,
  },
  input: {
    backgroundColor: '#2a2a2a',
    color: '#ffffff',
    fontSize: 16,
    padding: '4%',
    borderRadius: 12,
    borderWidth: 1,
    borderColor: '#3a3a3a',
    minHeight: 80,
    textAlignVertical: 'top',
  },
  button: {
    backgroundColor: '#6366f1',
    paddingVertical: '4%',
    paddingHorizontal: '8%',
    borderRadius: 12,
    alignItems: 'center',
    marginBottom: '5%',
  },
  buttonDisabled: {
    backgroundColor: '#4a4a4a',
  },
  buttonText: {
    color: '#ffffff',
    fontSize: 18,
    fontWeight: '600',
  },
  playlistInfo: {
    backgroundColor: '#2a2a2a',
    padding: '5%',
    borderRadius: 12,
    marginBottom: '5%',
  },
  infoTitle: {
    fontSize: 20,
    fontWeight: 'bold',
    color: '#ffffff',
    marginBottom: 12,
  },
  infoText: {
    fontSize: 16,
    color: '#b0b0b0',
    marginBottom: 8,
  },
  actionButtons: {
    flexDirection: 'row',
    marginTop: 20,
    gap: 12,
  },
  actionButton: {
    flex: 1,
  },
  primaryButton: {
    backgroundColor: '#6366f1',
    paddingVertical: 12,
    paddingHorizontal: 20,
    borderRadius: 8,
    alignItems: 'center',
  },
  secondaryButton: {
    backgroundColor: '#3a3a3a',
    paddingVertical: 12,
    paddingHorizontal: 20,
    borderRadius: 8,
    alignItems: 'center',
  },
  primaryButtonText: {
    color: '#ffffff',
    fontSize: 16,
    fontWeight: '600',
  },
  secondaryButtonText: {
    color: '#ffffff',
    fontSize: 16,
    fontWeight: '600',
  },
  footer: {
    alignItems: 'center',
    marginTop: 'auto',
    paddingTop: 20,
  },
  footerText: {
    fontSize: 14,
    color: '#808080',
    textAlign: 'center',
    lineHeight: 20,
  },
});

export default PlaylistScreen;
