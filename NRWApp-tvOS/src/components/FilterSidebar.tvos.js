/**
 * New Release Wall - tvOS Filter Sidebar Component
 * Left sidebar menu for filter options, accessible via Menu button
 */

import React, { useState, useRef, useCallback, useEffect } from 'react';
import {
  View,
  Text,
  StyleSheet,
  TouchableOpacity,
  Animated,
  Dimensions,
} from 'react-native';
import { Colors, Typography, Spacing } from '../constants/colors';
import { FOCUS_STYLES, useTVEventHandler, TV_EVENTS } from '../utils/focusManager.tvos';

const SCREEN_WIDTH = Dimensions.get('window').width;
const SIDEBAR_WIDTH = 320;

const FILTER_OPTIONS = [
  { id: 'all', label: 'All', icon: '🎬' },
  { id: 'big-time', label: 'Big Time Stuff', icon: '🎯' },
  { id: 'indie', label: 'Indie', icon: '💎' },
  { id: 'staff-picks', label: 'Staff Picks', icon: '⭐' },
  { id: 'foreign', label: 'Foreign', icon: '🌍' },
  { id: 'series', label: 'Limited Series', icon: '📺' },
  { id: 'restorations', label: 'Restorations & Reissues', icon: '🎞' },
  { id: 'documentary', label: 'Documentary', icon: '🎥' },
  { id: 'virtual-screenings', label: 'Virtual Screenings', icon: '🎪' },
];

const FilterSidebar = ({
  isVisible,
  activeFilter,
  onFilterChange,
  onClose,
}) => {
  const slideAnim = useRef(new Animated.Value(-SIDEBAR_WIDTH)).current;
  const fadeAnim = useRef(new Animated.Value(0)).current;

  // Handle TV remote events for closing sidebar
  useTVEventHandler({
    [TV_EVENTS.MENU]: () => {
      if (isVisible) {
        onClose();
      }
    },
    [TV_EVENTS.RIGHT]: () => {
      if (isVisible) {
        onClose();
      }
    },
  });

  // Animate sidebar visibility
  useEffect(() => {
    if (isVisible) {
      Animated.parallel([
        Animated.spring(slideAnim, {
          toValue: 0,
          friction: 10,
          tension: 80,
          useNativeDriver: true,
        }),
        Animated.timing(fadeAnim, {
          toValue: 1,
          duration: 200,
          useNativeDriver: true,
        }),
      ]).start();
    } else {
      Animated.parallel([
        Animated.spring(slideAnim, {
          toValue: -SIDEBAR_WIDTH,
          friction: 10,
          tension: 80,
          useNativeDriver: true,
        }),
        Animated.timing(fadeAnim, {
          toValue: 0,
          duration: 150,
          useNativeDriver: true,
        }),
      ]).start();
    }
  }, [isVisible, slideAnim, fadeAnim]);

  // Handle filter selection
  const handleFilterSelect = useCallback(
    (filterId) => {
      onFilterChange(filterId);
      onClose();
    },
    [onFilterChange, onClose]
  );

  if (!isVisible) {
    return null;
  }

  return (
    <View style={styles.overlay}>
      {/* Backdrop */}
      <Animated.View
        style={[
          styles.backdrop,
          {
            opacity: fadeAnim.interpolate({
              inputRange: [0, 1],
              outputRange: [0, 0.6],
            }),
          },
        ]}
      >
        <TouchableOpacity
          style={StyleSheet.absoluteFill}
          onPress={onClose}
          activeOpacity={1}
          accessible={false}
        />
      </Animated.View>

      {/* Sidebar */}
      <Animated.View
        style={[
          styles.sidebar,
          {
            transform: [{ translateX: slideAnim }],
          },
        ]}
      >
        {/* Header */}
        <View style={styles.header}>
          <Text style={styles.headerTitle}>Filters</Text>
        </View>

        {/* Filter options */}
        <View style={styles.options}>
          {FILTER_OPTIONS.map((filter, index) => (
            <FilterOption
              key={filter.id}
              filter={filter}
              isActive={activeFilter === filter.id}
              onSelect={() => handleFilterSelect(filter.id)}
              hasTVPreferredFocus={index === 0 && isVisible}
            />
          ))}
        </View>

        {/* Footer hint */}
        <View style={styles.footer}>
          <Text style={styles.footerText}>
            Press Menu or → to close
          </Text>
        </View>
      </Animated.View>
    </View>
  );
};

// Individual filter option component
const FilterOption = ({
  filter,
  isActive,
  onSelect,
  hasTVPreferredFocus,
}) => {
  const [isFocused, setIsFocused] = useState(false);
  const scaleAnim = useRef(new Animated.Value(1)).current;

  const handleFocus = useCallback(() => {
    setIsFocused(true);
    Animated.spring(scaleAnim, {
      toValue: FOCUS_STYLES.menuItem.scale,
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

  return (
    <TouchableOpacity
      onPress={onSelect}
      onFocus={handleFocus}
      onBlur={handleBlur}
      hasTVPreferredFocus={hasTVPreferredFocus}
      activeOpacity={0.9}
      accessible={true}
      accessibilityLabel={`Filter by ${filter.label}`}
      accessibilityRole="button"
      accessibilityState={{ selected: isActive }}
    >
      <Animated.View
        style={[
          styles.option,
          {
            backgroundColor: isFocused
              ? Colors.primary
              : isActive
              ? Colors.backgroundTertiary
              : 'transparent',
            borderColor: isFocused
              ? Colors.primary
              : isActive
              ? Colors.primary
              : 'transparent',
            transform: [{ scale: scaleAnim }],
          },
        ]}
      >
        <Text
          style={[
            styles.optionIcon,
            {
              color: isFocused ? Colors.background : Colors.textPrimary,
            },
          ]}
        >
          {filter.icon}
        </Text>
        <Text
          style={[
            styles.optionLabel,
            {
              color: isFocused ? Colors.background : Colors.textPrimary,
              fontWeight: isActive ? '700' : '500',
            },
          ]}
        >
          {filter.label}
        </Text>
        {isActive && !isFocused && (
          <View style={styles.activeIndicator} />
        )}
      </Animated.View>
    </TouchableOpacity>
  );
};

const styles = StyleSheet.create({
  overlay: {
    ...StyleSheet.absoluteFillObject,
    zIndex: 1000,
  },
  backdrop: {
    ...StyleSheet.absoluteFillObject,
    backgroundColor: Colors.background,
  },
  sidebar: {
    position: 'absolute',
    left: 0,
    top: 0,
    bottom: 0,
    width: SIDEBAR_WIDTH,
    backgroundColor: Colors.backgroundSecondary,
    paddingTop: Spacing.tvos.xl,
    paddingHorizontal: Spacing.tvos.lg,
    borderRightWidth: 1,
    borderRightColor: Colors.backgroundTertiary,
  },
  header: {
    marginBottom: Spacing.tvos.xl,
  },
  headerTitle: {
    color: Colors.textPrimary,
    fontSize: Typography.tvos.subtitle,
    fontWeight: '700',
  },
  options: {
    flex: 1,
  },
  option: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingHorizontal: Spacing.tvos.md,
    paddingVertical: Spacing.tvos.md,
    borderRadius: 12,
    borderWidth: 2,
    marginBottom: Spacing.tvos.sm,
  },
  optionIcon: {
    fontSize: Typography.tvos.body,
    marginRight: Spacing.tvos.md,
    width: 32,
    textAlign: 'center',
  },
  optionLabel: {
    fontSize: Typography.tvos.body,
    flex: 1,
  },
  activeIndicator: {
    width: 8,
    height: 8,
    borderRadius: 4,
    backgroundColor: Colors.primary,
    marginLeft: Spacing.tvos.sm,
  },
  footer: {
    paddingVertical: Spacing.tvos.lg,
    borderTopWidth: 1,
    borderTopColor: Colors.backgroundTertiary,
  },
  footerText: {
    color: Colors.textMuted,
    fontSize: Typography.tvos.caption,
    textAlign: 'center',
  },
});

export default FilterSidebar;
