const { getDefaultConfig, mergeConfig } = require('@react-native/metro-config');

/**
 * Metro configuration for New Release Wall
 * https://facebook.github.io/metro/docs/configuration
 *
 * @type {import('metro-config').MetroConfig}
 */
const config = {
  // Add any custom configuration here
  resolver: {
    // Support for tvOS platform extensions
    sourceExts: ['tvos.js', 'tvos.ts', 'tvos.tsx', 'js', 'json', 'ts', 'tsx'],
  },
};

module.exports = mergeConfig(getDefaultConfig(__dirname), config);
