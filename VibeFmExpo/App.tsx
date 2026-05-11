import React from 'react';
import { NavigationContainer } from '@react-navigation/native';
import { createStackNavigator } from '@react-navigation/stack';
import { StackNavigationProp } from '@react-navigation/stack';
import PlaylistScreen from './src/screens/PlaylistScreen';
import PlayerScreen from './src/screens/PlayerScreen';
import QueueScreen from './src/screens/QueueScreen';
import { LoadPlaylistResponse } from './src/types';

type RootStackParamList = {
  Playlist: undefined;
  Player: { playlist: LoadPlaylistResponse };
  Queue: undefined;
};

const Stack = createStackNavigator<RootStackParamList>();

const App: React.FC = () => {
  return (
    <NavigationContainer>
      <Stack.Navigator
        initialRouteName="Playlist"
        screenOptions={{
          headerShown: false,
          cardStyle: { backgroundColor: '#1a1a1a' },
        }}
      >
        <Stack.Screen 
          name="Playlist" 
          component={PlaylistScreen}
          options={{
            gestureEnabled: false,
          }}
        />
        <Stack.Screen 
          name="Player" 
          component={PlayerScreen}
          options={{
            gestureEnabled: true,
            presentation: 'modal',
          }}
        />
        <Stack.Screen 
          name="Queue" 
          component={QueueScreen}
          options={{
            gestureEnabled: true,
            presentation: 'modal',
          }}
        />
      </Stack.Navigator>
    </NavigationContainer>
  );
};

export default App;
