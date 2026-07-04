/**
 * New Release Wall - Main App Component
 * Sets up navigation and global providers
 */

import React, { useEffect, useRef } from 'react';
import { Platform, StatusBar, View, StyleSheet, AppState, LogBox } from 'react-native';
import { NavigationContainer } from '@react-navigation/native';
import { createNativeStackNavigator } from '@react-navigation/native-stack';
import { SafeAreaProvider } from 'react-native-safe-area-context';

// Import screens (React Native automatically picks .tvos.js on tvOS)
import HomeScreen from './src/screens/HomeScreen.tvos';
import MovieDetail from './src/screens/MovieDetail.tvos';
import SearchScreen from './src/screens/SearchScreen.tvos';
import TrailerScreen from './src/screens/TrailerScreen.tvos';

// Import constants
import { Colors } from './src/constants/colors';

// Import services
import { initializeAnalytics, trackSessionStart, trackSessionEnd } from './src/services/analytics.tvos';
import { initializeSentry } from './src/services/sentry.tvos';

// Suppress AsyncStorage warning on tvOS (storage works but may be cleared by system)
LogBox.ignoreLogs(['Persistent storage is not supported on tvOS']);

// Create navigation stack
const Stack = createNativeStackNavigator();

// Deep linking configuration for nrw:// scheme
const linking = {
  prefixes: ['nrw://', 'https://newreleasewall.com'],
  config: {
    screens: {
      Home: '',
      MovieDetail: 'movie/:id',
      Search: 'search',
    },
  },
};

// Navigation theme (dark mode)
const navigationTheme = {
  dark: true,
  colors: {
    primary: Colors.primary,
    background: Colors.background,
    card: Colors.backgroundSecondary,
    text: Colors.textPrimary,
    border: Colors.backgroundTertiary,
    notification: Colors.primary,
  },
};

// Screen options for tvOS
const screenOptions = {
  headerShown: false, // Hide header (tvOS doesn't use navigation bars)
  animation: 'fade',
  contentStyle: {
    backgroundColor: Colors.background,
  },
};

const App = () => {
  const navigationRef = useRef(null);
  const sessionStartTime = useRef(null);

  // Initialize services on mount
  useEffect(() => {
    initializeServices();
  }, []);

  // Track session lifecycle
  useEffect(() => {
    // Track session start
    sessionStartTime.current = Date.now();
    trackSessionStart();

    // Track session end on app state change
    const subscription = AppState.addEventListener('change', (nextAppState) => {
      if (nextAppState === 'background' || nextAppState === 'inactive') {
        if (sessionStartTime.current) {
          const duration = Math.floor((Date.now() - sessionStartTime.current) / 1000);
          trackSessionEnd(duration);
        }
      } else if (nextAppState === 'active') {
        sessionStartTime.current = Date.now();
        trackSessionStart();
      }
    });

    return () => {
      subscription.remove();
      // Track final session end on unmount
      if (sessionStartTime.current) {
        const duration = Math.floor((Date.now() - sessionStartTime.current) / 1000);
        trackSessionEnd(duration);
      }
    };
  }, []);

  return (
    <SafeAreaProvider>
      <View style={styles.container}>
        {/* Status bar (hidden on tvOS) */}
        {!Platform.isTV && (
          <StatusBar
            barStyle="light-content"
            backgroundColor={Colors.background}
          />
        )}

        {/* Navigation */}
        <NavigationContainer
          ref={navigationRef}
          theme={navigationTheme}
          linking={linking}
        >
          <Stack.Navigator
            initialRouteName="Home"
            screenOptions={screenOptions}
          >
            <Stack.Screen
              name="Home"
              component={HomeScreen}
              options={{
                title: 'New Release Wall',
              }}
            />
            <Stack.Screen
              name="MovieDetail"
              component={MovieDetail}
              options={({ route }) => ({
                title: route.params?.movie?.title || 'Movie Details',
              })}
            />
            <Stack.Screen
              name="Search"
              component={SearchScreen}
              options={{
                title: 'Search',
                // tvOS: Menu must NOT natively pop this route — the screen owns
                // the Menu key in JS for progressive back (clear query → exit).
                // react-native-screens maps the tvOS menu-pop as its back
                // "gesture", so this disables exactly that native path.
                gestureEnabled: false,
              }}
            />
            <Stack.Screen
              name="Trailer"
              component={TrailerScreen}
              options={{
                title: 'Trailer',
              }}
            />
          </Stack.Navigator>
        </NavigationContainer>
      </View>
    </SafeAreaProvider>
  );
};

// Initialize third-party services
async function initializeServices() {
  try {
    // Initialize analytics
    await initializeAnalytics();
    console.log('[App] Analytics initialized');

    // Initialize crash reporting
    await initializeSentry();
    console.log('[App] Sentry initialized');
  } catch (error) {
    console.error('[App] Error initializing services:', error);
  }
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: Colors.background,
  },
});

export default App;
