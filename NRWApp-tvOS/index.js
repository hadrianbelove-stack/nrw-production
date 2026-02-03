/**
 * New Release Wall - Entry Point
 * React Native app for iOS and tvOS
 */

import { AppRegistry, Platform } from 'react-native';
import App from './App';
import { name as appName } from './app.json';

// Register the app
AppRegistry.registerComponent(appName, () => App);

// Enable TV mode for tvOS
if (Platform.isTV) {
  console.log('[NRW] Running on tvOS');
}
