/**
 * New Release Wall - iOS App
 * Curated new releases you won't find elsewhere
 */

import React from 'react';
import {NavigationContainer} from '@react-navigation/native';
import {createNativeStackNavigator} from '@react-navigation/native-stack';
import {SafeAreaProvider} from 'react-native-safe-area-context';
import {StatusBar} from 'react-native';

import HomeScreen from './src/screens/HomeScreen';
import MovieDetail from './src/screens/MovieDetail';
import {Colors} from './src/constants/colors';

const Stack = createNativeStackNavigator();

const screenOptions = {
  headerStyle: {
    backgroundColor: Colors.background,
  },
  headerTintColor: Colors.primary,
  headerTitleStyle: {
    fontWeight: '600',
    color: Colors.textPrimary,
  },
  contentStyle: {
    backgroundColor: Colors.background,
  },
};

export default function App() {
  return (
    <SafeAreaProvider>
      <StatusBar barStyle="light-content" backgroundColor={Colors.background} />
      <NavigationContainer
        theme={{
          dark: true,
          colors: {
            primary: Colors.primary,
            background: Colors.background,
            card: Colors.backgroundSecondary,
            text: Colors.textPrimary,
            border: Colors.backgroundTertiary,
            notification: Colors.primary,
          },
        }}>
        <Stack.Navigator screenOptions={screenOptions}>
          <Stack.Screen
            name="Home"
            component={HomeScreen}
            options={{
              title: 'NEW RELEASE WALL',
              headerLargeTitle: true,
            }}
          />
          <Stack.Screen
            name="MovieDetail"
            component={MovieDetail}
            options={({route}) => ({
              title: route.params?.movie?.title || 'Movie Details',
            })}
          />
        </Stack.Navigator>
      </NavigationContainer>
    </SafeAreaProvider>
  );
}
