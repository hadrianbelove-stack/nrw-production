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

// Service logo mapping
// Logos are optional - the component falls back to text initials when missing
// To enable logos, add PNG files to assets/logos/ and uncomment the requires below
const SERVICE_LOGOS = {
  // Uncomment these lines after adding the corresponding PNG files:
  // amazon: require('../../assets/logos/amazon.png'),
  // apple_tv: require('../../assets/logos/apple-tv.png'),
  // netflix: require('../../assets/logos/netflix.png'),
  // hulu: require('../../assets/logos/hulu.png'),
  // max: require('../../assets/logos/max.png'),
  // disney_plus: require('../../assets/logos/disney-plus.png'),
  // peacock: require('../../assets/logos/peacock.png'),
  // paramount_plus: require('../../assets/logos/paramount-plus.png'),
  // mubi: require('../../assets/logos/mubi.png'),
  // criterion: require('../../assets/logos/criterion.png'),
  // vix: require('../../assets/logos/vix.png'),
  // angel_studios: require('../../assets/logos/angel-studios.png'),
  // shudder: require('../../assets/logos/shudder.png'),
  // fandango: require('../../assets/logos/fandango.png'),
};

// Fallback service logos using text (brand colors)
const SERVICE_COLORS = {
  amazon: '#ff9900',
  apple_tv: '#000000',
  netflix: '#e50914',
  hulu: '#1ce783',
  max: '#741dda',
  disney_plus: '#113ccf',
  peacock: '#000000',
  paramount_plus: '#0064ff',
  mubi: '#00e0ff',
  criterion: '#000000',
  vix: '#ff6600',
  angel_studios: '#ffffff',
  shudder: '#c91e1e',
  fandango: '#ff7300',
  strand_releasing: '#8b0000',
  plex: '#E5A00D',
};

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

  // Determine button color based on type
  const buttonColor = type === 'purchase' ? Colors.orange : Colors.teal;
  const serviceColor = SERVICE_COLORS[service] || buttonColor;

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
            backgroundColor: isFocused ? buttonColor : Colors.backgroundTertiary,
            transform: [{ scale: scaleAnim }],
            opacity: disabled ? 0.5 : 1,
          },
        ]}
      >
        {/* Glow effect (visible when focused) */}
        <Animated.View
          style={[
            styles.glowLayer,
            {
              opacity: glowOpacity,
              shadowColor: buttonColor,
            },
          ]}
        />

        {/* Service logo or icon */}
        <View style={styles.iconContainer}>
          <ServiceIcon service={service} isFocused={isFocused} />
        </View>

        {/* Button label */}
        <Text
          style={[
            styles.label,
            {
              color: isFocused ? Colors.background : Colors.textPrimary,
            },
          ]}
          numberOfLines={1}
        >
          {displayLabel}
        </Text>
      </Animated.View>
    </TouchableOpacity>
  );
};

// Service icon component (shows logo or fallback text)
const ServiceIcon = ({ service, isFocused }) => {
  // Try to use logo image, fallback to text
  const hasLogo = SERVICE_LOGOS[service];
  const serviceColor = SERVICE_COLORS[service] || Colors.textPrimary;

  if (hasLogo) {
    try {
      return (
        <Image
          source={SERVICE_LOGOS[service]}
          style={[
            styles.logo,
            { tintColor: isFocused ? Colors.background : undefined },
          ]}
          resizeMode="contain"
        />
      );
    } catch {
      // Fallback to text if image fails
    }
  }

  // Text fallback
  return (
    <Text
      style={[
        styles.iconText,
        {
          color: isFocused ? Colors.background : serviceColor,
        },
      ]}
    >
      {getServiceInitial(service)}
    </Text>
  );
};

// Get service initial for fallback icon
function getServiceInitial(service) {
  const initials = {
    amazon: 'A',
    apple_tv: '▶',
    netflix: 'N',
    hulu: 'H',
    max: 'M',
    disney_plus: 'D+',
    peacock: 'P',
    paramount_plus: 'P+',
    mubi: 'M',
    criterion: 'C',
    vix: 'V',
    angel_studios: 'A',
    shudder: 'S',
    fandango: 'F',
    strand_releasing: 'SR',
    plex: '▶',
  };
  return initials[service] || service?.charAt(0)?.toUpperCase() || '?';
}

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
    plex: 'Plex',
  };

  const serviceName = serviceNames[service] || service;
  // Plex uses "Play on" instead of "Watch on" or "Rent on"
  const action = type === 'plex' ? 'Play on' : (type === 'purchase' ? 'Rent on' : 'Watch on');

  return `${action} ${serviceName}`;
}

// Info button variant for trailer, RT, Wikipedia
export const InfoButton = ({
  type,
  label,
  onPress,
  hasTVPreferredFocus = false,
  testID,
}) => {
  const [isFocused, setIsFocused] = useState(false);
  const scaleAnim = useRef(new Animated.Value(1)).current;

  const handleFocus = useCallback(() => {
    setIsFocused(true);
    Animated.spring(scaleAnim, {
      toValue: 1.1,
      friction: 8,
      tension: 100,
      useNativeDriver: true,
    }).start();
  }, [scaleAnim]);

  const handleBlur = useCallback(() => {
    setIsFocused(false);
    Animated.spring(scaleAnim, {
      toValue: 1,
      friction: 8,
      tension: 100,
      useNativeDriver: true,
    }).start();
  }, [scaleAnim]);

  const getIcon = () => {
    switch (type) {
      case 'trailer':
        return '▶';
      case 'rotten_tomatoes':
        return '🍅';
      case 'wikipedia':
        return 'W';
      default:
        return '?';
    }
  };

  const defaultLabels = {
    trailer: 'Watch Trailer',
    rotten_tomatoes: 'Rotten Tomatoes',
    wikipedia: 'Wikipedia',
  };

  return (
    <TouchableOpacity
      onPress={onPress}
      onFocus={handleFocus}
      onBlur={handleBlur}
      hasTVPreferredFocus={hasTVPreferredFocus}
      activeOpacity={0.9}
      accessible={true}
      accessibilityLabel={label || defaultLabels[type]}
      accessibilityRole="button"
      testID={testID}
    >
      <Animated.View
        style={[
          styles.infoButton,
          {
            backgroundColor: isFocused
              ? Colors.backgroundTertiary
              : 'transparent',
            borderColor: isFocused ? Colors.primary : Colors.textMuted,
            transform: [{ scale: scaleAnim }],
          },
        ]}
      >
        <Text
          style={[
            styles.infoIcon,
            { color: isFocused ? Colors.primary : Colors.textSecondary },
          ]}
        >
          {getIcon()}
        </Text>
        <Text
          style={[
            styles.infoLabel,
            { color: isFocused ? Colors.primary : Colors.textSecondary },
          ]}
        >
          {label || defaultLabels[type]}
        </Text>
      </Animated.View>
    </TouchableOpacity>
  );
};

const styles = StyleSheet.create({
  container: {
    flexDirection: 'row',
    alignItems: 'center',
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
  iconContainer: {
    width: 40,
    height: 40,
    justifyContent: 'center',
    alignItems: 'center',
    marginRight: Spacing.tvos.md,
  },
  logo: {
    width: 32,
    height: 32,
  },
  iconText: {
    fontSize: Typography.tvos.body,
    fontWeight: '700',
  },
  label: {
    fontSize: Typography.tvos.button,
    fontWeight: '600',
    flex: 1,
  },
  infoButton: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingHorizontal: Spacing.tvos.md,
    paddingVertical: Spacing.tvos.sm,
    borderRadius: 8,
    borderWidth: 2,
    marginRight: Spacing.tvos.md,
  },
  infoIcon: {
    fontSize: Typography.tvos.body,
    marginRight: Spacing.tvos.sm,
  },
  infoLabel: {
    fontSize: Typography.tvos.caption,
    fontWeight: '500',
  },
});

export default WatchButton;
