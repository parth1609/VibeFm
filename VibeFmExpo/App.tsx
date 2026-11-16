import React from 'react';
import { NavigationContainer, DarkTheme } from '@react-navigation/native';
import { createStackNavigator } from '@react-navigation/stack';
import { SafeAreaProvider } from 'react-native-safe-area-context';
import { StatusBar } from 'expo-status-bar';
import PlaylistScreen from './src/screens/PlaylistScreen';
import PlayerScreen from './src/screens/PlayerScreen';
import QueueScreen from './src/screens/QueueScreen';
import { LoadPlaylistResponse } from './src/types';
import { colors } from './src/styles/colors';

type RootStackParamList = {
  Playlist: undefined;
  Player: { playlist: LoadPlaylistResponse };
  Queue: undefined;
};

const Stack = createStackNavigator<RootStackParamList>();

const theme = {
  ...DarkTheme,
  colors: {
    ...DarkTheme.colors,
    background: colors.background,
    card: colors.background,
    text: colors.text,
    border: colors.border,
    primary: colors.primary,
  },
};

const App: React.FC = () => {
  return (
    <SafeAreaProvider>
      <NavigationContainer theme={theme}>
        <StatusBar style="light" />
        <Stack.Navigator
          initialRouteName="Playlist"
          screenOptions={{
            headerShown: false,
            cardStyle: { backgroundColor: colors.background },
          }}
        >
          <Stack.Screen
            name="Playlist"
            component={PlaylistScreen}
            options={{ gestureEnabled: false }}
          />
          <Stack.Screen
            name="Player"
            component={PlayerScreen}
            options={{ gestureEnabled: true, presentation: 'modal' }}
          />
          <Stack.Screen
            name="Queue"
            component={QueueScreen}
            options={{ gestureEnabled: true, presentation: 'modal' }}
          />
        </Stack.Navigator>
      </NavigationContainer>
    </SafeAreaProvider>
  );
};

export default App;
