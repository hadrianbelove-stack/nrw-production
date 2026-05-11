/**
 * New Release Wall - Entry Point
 * React Native app for iOS and tvOS
 */

// Polyfill TextEncoder/TextDecoder — required by react-native-qrcode-svg on Hermes/tvOS
import { TextEncoder, TextDecoder } from 'text-encoding';
if (typeof global.TextEncoder === 'undefined') {
  global.TextEncoder = TextEncoder;
  global.TextDecoder = TextDecoder;
}

import { AppRegistry, Platform } from 'react-native';
import App from './App';
import { name as appName } from './app.json';

// Register the app
AppRegistry.registerComponent(appName, () => App);

// Enable TV mode for tvOS
if (Platform.isTV) {
  console.log('[NRW] Running on tvOS');
}
