/**
 * New Release Wall - tvOS Watch Button Component
 * Focusable button with glow effect for VOD services
 */

import React, { useState, useRef, useCallback } from 'react';
import {
  View,
  Text,
  Image,
  StyleSheet,
  TouchableOpacity,
  Animated,
} from 'react-native';
import { Colors, Typography, Spacing } from '../constants/colors';
import { FOCUS_STYLES } from '../utils/focusManager.tvos';

// Service logo images (white logos on brand-color backgrounds)
const SERVICE_LOGOS = {
  amazon: require('../../assets/logos/services/amazon.png'),
  apple_tv: require('../../assets/logos/services/apple_tv.png'),
  netflix: require('../../assets/logos/services/netflix.png'),
  prime_video: require('../../assets/logos/services/prime_video.png'),
  hulu: require('../../assets/logos/services/hulu.png'),
  max: require('../../assets/logos/services/max.png'),
  disney_plus: require('../../assets/logos/services/disney_plus.png'),
  peacock: require('../../assets/logos/services/peacock.png'),
  paramount_plus: require('../../assets/logos/services/paramount_plus.png'),
  mubi: require('../../assets/logos/services/mubi.png'),
  criterion: require('../../assets/logos/services/criterion.png'),
  amc: require('../../assets/logos/services/amc.png'),
  fandango: require('../../assets/logos/services/fandango.png'),
  plex: require('../../assets/logos/services/plex.png'),
};

// Brand colors for filled button backgrounds
const SERVICE_COLORS = {
  amazon: '#ff9900',
  apple_tv: '#000000',
  netflix: '#e50914',
  hulu: '#1ce783',
  max: '#B537F2',
  disney_plus: '#113ccf',
  peacock: '#000000',
  paramount_plus: '#0064ff',
  mubi: '#DA2128',
  criterion: '#000000',
  vix: '#ff6600',
  angel_studios: '#ffffff',
  shudder: '#8B0000',
  fandango: '#ff7300',
  strand_releasing: '#8b0000',
  tubi: '#FA382F',
  plex: '#E5A00D',
  amc: '#1BB74B',
};

// Services that need a visible border on dark backgrounds (black bg buttons)
const NEEDS_BORDER = ['apple_tv', 'peacock', 'criterion'];

const WatchButton = ({
  service,
  label,
  type = 'purchase', // 'purchase' or 'streaming'
  onPress,
  hasTVPreferredFocus = false,
  disabled = false,
  testID,
}) => {
  const [isFocused, setIsFocused] = useState(false);
  const scaleAnim = useRef(new Animated.Value(1)).current;
  const glowAnim = useRef(new Animated.Value(0)).current;

  // Use service brand color for filled button background
  const serviceColor = SERVICE_COLORS[service] || (type === 'purchase' ? Colors.orange : Colors.teal);
  const hasBorder = NEEDS_BORDER.includes(service);

  // Handle focus
  const handleFocus = useCallback(() => {
    setIsFocused(true);

    Animated.parallel([
      Animated.spring(scaleAnim, {
        toValue: FOCUS_STYLES.button.scale,
        friction: 8,
        tension: 100,
        useNativeDriver: true,
      }),
      Animated.timing(glowAnim, {
        toValue: 1,
        duration: 150,
        useNativeDriver: false,
      }),
    ]).start();
  }, [scaleAnim, glowAnim]);

  // Handle blur
  const handleBlur = useCallback(() => {
    setIsFocused(false);

    Animated.parallel([
      Animated.spring(scaleAnim, {
        toValue: 1,
        friction: 8,
        tension: 100,
        useNativeDriver: true,
      }),
      Animated.timing(glowAnim, {
        toValue: 0,
        duration: 150,
        useNativeDriver: false,
      }),
    ]).start();
  }, [scaleAnim, glowAnim]);

  // Interpolate glow opacity
  const glowOpacity = glowAnim.interpolate({
    inputRange: [0, 1],
    outputRange: [0, 0.6],
  });

  // Get service label
  const displayLabel = label || getDefaultLabel(service, type);

  return (
    <TouchableOpacity
      onPress={onPress}
      onFocus={handleFocus}
      onBlur={handleBlur}
      hasTVPreferredFocus={hasTVPreferredFocus}
      activeOpacity={0.9}
      disabled={disabled}
      accessible={true}
      accessibilityLabel={displayLabel}
      accessibilityRole="button"
      accessibilityState={{ disabled }}
      testID={testID}
    >
      <Animated.View
        style={[
          styles.container,
          {
            backgroundColor: serviceColor,
            transform: [{ scale: scaleAnim }],
            opacity: disabled ? 0.5 : 1,
          },
          hasBorder && { borderWidth: 1, borderColor: '#444' },
        ]}
      >
        {/* Glow effect (visible when focused) */}
        <Animated.View
          style={[
            styles.glowLayer,
            {
              opacity: glowOpacity,
              shadowColor: serviceColor,
            },
          ]}
        />

        {/* Logo image or text fallback */}
        {SERVICE_LOGOS[service] ? (
          <Image
            source={SERVICE_LOGOS[service]}
            style={styles.logo}
            tintColor="#ffffff"
            resizeMode="contain"
          />
        ) : (
          <Text
            style={[
              styles.label,
              {
                color: service === 'hulu' ? '#000000' : '#ffffff',
                textAlign: 'center',
              },
            ]}
            numberOfLines={1}
          >
            {displayLabel}
          </Text>
        )}
      </Animated.View>
    </TouchableOpacity>
  );
};

// Get default label for service
function getDefaultLabel(service, type) {
  const serviceNames = {
    amazon: 'Amazon',
    apple_tv: 'Apple TV',
    netflix: 'Netflix',
    hulu: 'Hulu',
    max: 'Max',
    disney_plus: 'Disney+',
    peacock: 'Peacock',
    paramount_plus: 'Paramount+',
    mubi: 'MUBI',
    criterion: 'Criterion',
    vix: 'VIX',
    angel_studios: 'Angel Studios',
    shudder: 'Shudder',
    fandango: 'Fandango',
    strand_releasing: 'Strand Releasing',
    tubi: 'Tubi',
    plex: 'Plex',
  };

  const serviceName = serviceNames[service] || service;
  // Plex uses "Play on" instead of "Watch on" or "Rent on"
  const action = type === 'plex' ? 'Play on' : (type === 'purchase' ? 'Rent on' : 'Watch on');

  return `${action} ${serviceName}`;
}

const styles = StyleSheet.create({
  container: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    paddingHorizontal: Spacing.tvos.lg,
    paddingVertical: Spacing.tvos.md,
    borderRadius: 12,
    minWidth: 240,
    marginRight: Spacing.tvos.md,
    marginBottom: Spacing.tvos.sm,
  },
  glowLayer: {
    ...StyleSheet.absoluteFillObject,
    borderRadius: 12,
    shadowOffset: { width: 0, height: 0 },
    shadowOpacity: 1,
    shadowRadius: 20,
  },
  logo: {
    width: 160,
    height: 40,
  },
  label: {
    fontSize: Typography.tvos.button,
    fontWeight: '700',
    letterSpacing: 1,
  },
});

export default WatchButton;
