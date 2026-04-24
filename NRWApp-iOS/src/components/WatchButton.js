/**
 * New Release Wall - Watch Button Component
 * VOD service buttons for renting/streaming
 */

import React from 'react';
import {Text, StyleSheet, TouchableOpacity, View} from 'react-native';
import {Colors, Typography, Spacing} from '../constants/colors';

// Service display names and colors
const SERVICE_CONFIG = {
  amazon: {
    name: 'Amazon',
    color: Colors.amazonOrange,
    textColor: '#000000',
  },
  apple_tv: {
    name: 'Apple TV',
    color: '#000000',
    textColor: '#ffffff',
    borderColor: '#ffffff',
  },
  netflix: {
    name: 'Netflix',
    color: '#e50914',
    textColor: '#ffffff',
  },
  hulu: {
    name: 'Hulu',
    color: '#1ce783',
    textColor: '#000000',
  },
  max: {
    name: 'Max',
    color: '#B537F2',
    textColor: '#ffffff',
  },
  disney_plus: {
    name: 'Disney+',
    color: '#113ccf',
    textColor: '#ffffff',
  },
  peacock: {
    name: 'Peacock',
    color: '#000000',
    textColor: '#ffffff',
    borderColor: '#444444',
  },
  paramount_plus: {
    name: 'Paramount+',
    color: '#0064ff',
    textColor: '#ffffff',
  },
  mubi: {
    name: 'MUBI',
    color: '#DA2128',
    textColor: '#ffffff',
  },
  criterion: {
    name: 'Criterion',
    color: '#000000',
    textColor: '#ffffff',
    borderColor: '#444444',
  },
  tubi: {
    name: 'Tubi',
    color: '#FA382F',
    textColor: '#ffffff',
  },
  fawesome: {
    name: 'Fawesome',
    color: '#5B8DEF',
    textColor: '#ffffff',
  },
  fandango: {
    name: 'Fandango',
    color: '#ff6600',
    textColor: '#ffffff',
  },
  vod: {
    name: 'Rent/Buy',
    color: Colors.orange,
    textColor: '#000000',
  },
  streaming: {
    name: 'Stream',
    color: Colors.primary,
    textColor: '#000000',
  },
};

export default function WatchButton({link, onPress, size = 'medium'}) {
  if (!link || !link.url) return null;

  const config = SERVICE_CONFIG[link.service] || SERVICE_CONFIG.vod;
  const isStreaming = link.type === 'streaming';

  const isScreeningButton = link.labelOverride === 'Buy Ticket';

  const buttonStyle = [
    styles.button,
    size === 'small' && styles.buttonSmall,
    size === 'large' && styles.buttonLarge,
    isScreeningButton
      ? {backgroundColor: 'transparent', borderWidth: 2, borderColor: '#FFD700'}
      : {backgroundColor: config.color},
    !isScreeningButton && config.borderColor && {borderWidth: 1, borderColor: config.borderColor},
  ];

  const textStyle = [
    styles.buttonText,
    size === 'small' && styles.buttonTextSmall,
    size === 'large' && styles.buttonTextLarge,
    {color: isScreeningButton ? '#FFD700' : config.textColor},
  ];

  // Determine label
  let label = config.name;
  if (link.labelOverride) {
    label = link.labelOverride;
  } else if (isStreaming) {
    label = `Watch on ${config.name}`;
  } else {
    label = `Rent on ${config.name}`;
  }

  // Use short label for small size (unless overridden)
  if (size === 'small' && !link.labelOverride) {
    label = config.name;
  }

  return (
    <TouchableOpacity
      style={buttonStyle}
      onPress={() => onPress?.(link)}
      activeOpacity={0.8}>
      <View style={styles.buttonContent}>
        <Text style={textStyle} numberOfLines={1}>
          {label}
        </Text>
        {isStreaming && (
          <View style={styles.streamBadge}>
            <Text style={styles.streamBadgeText}>INCLUDED</Text>
          </View>
        )}
      </View>
    </TouchableOpacity>
  );
}

/**
 * Render multiple watch buttons
 */
export function WatchButtonGroup({links, onPress, maxButtons = 3}) {
  if (!links || links.length === 0) {
    return (
      <View style={styles.noLinks}>
        <Text style={styles.noLinksText}>No streaming options available</Text>
      </View>
    );
  }

  // Show up to maxButtons
  const displayLinks = links.slice(0, maxButtons);

  return (
    <View style={styles.buttonGroup}>
      {displayLinks.map((link, index) => (
        <WatchButton
          key={`${link.service}-${index}`}
          link={link}
          onPress={onPress}
          size={displayLinks.length > 2 ? 'small' : 'medium'}
        />
      ))}
      {links.length > maxButtons && (
        <Text style={styles.moreText}>
          +{links.length - maxButtons} more options
        </Text>
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  button: {
    paddingVertical: Spacing.sm + 2,
    paddingHorizontal: Spacing.md,
    borderRadius: 8,
    marginBottom: Spacing.sm,
    minWidth: 120,
  },
  buttonSmall: {
    paddingVertical: Spacing.sm,
    paddingHorizontal: Spacing.sm + 4,
    minWidth: 90,
  },
  buttonLarge: {
    paddingVertical: Spacing.md,
    paddingHorizontal: Spacing.lg,
    minWidth: 160,
  },
  buttonContent: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
  },
  buttonText: {
    fontSize: Typography.button,
    fontWeight: '600',
    textAlign: 'center',
  },
  buttonTextSmall: {
    fontSize: Typography.caption,
  },
  buttonTextLarge: {
    fontSize: Typography.body,
  },
  streamBadge: {
    backgroundColor: 'rgba(255,255,255,0.2)',
    paddingHorizontal: 6,
    paddingVertical: 2,
    borderRadius: 4,
    marginLeft: 8,
  },
  streamBadgeText: {
    color: '#ffffff',
    fontSize: 9,
    fontWeight: '700',
  },
  buttonGroup: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: Spacing.sm,
  },
  noLinks: {
    paddingVertical: Spacing.lg,
    alignItems: 'center',
  },
  noLinksText: {
    color: Colors.textMuted,
    fontSize: Typography.body,
  },
  moreText: {
    color: Colors.textSecondary,
    fontSize: Typography.caption,
    alignSelf: 'center',
    marginLeft: Spacing.sm,
  },
});
