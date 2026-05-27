/**
 * New Release Wall - Filter Bar Component
 * Horizontal scrollable filter buttons
 */

import React from 'react';
import {View, Text, StyleSheet, ScrollView, TouchableOpacity} from 'react-native';
import {Colors, Typography, Spacing} from '../constants/colors';

const FILTERS = [
  {id: 'staff-picks', label: 'NRW Picks'},
  {id: 'studio', label: 'Studio'},
  {id: 'indie', label: 'Indie'},
  {id: 'exploitation', label: 'Exploitation'},
  {id: 'foreign', label: 'Foreign'},
  {id: 'documentary', label: 'Docs'},
  {id: 'series', label: 'Miniseries'},
  {id: 'restorations', label: 'Reissues'},
  {id: 'virtual-screenings', label: 'V. Screenings'},
  {id: 'pre-orders', label: 'Pre-Orders'},
];

export default function FilterBar({activeFilters, onFilterChange, slopFree, onSlopFreeChange}) {
  return (
    <View style={styles.container}>
      <ScrollView
        horizontal
        showsHorizontalScrollIndicator={false}
        contentContainerStyle={styles.scrollContent}>
        {FILTERS.map(filter => (
          <FilterButton
            key={filter.id}
            label={filter.label}
            isSelected={activeFilters.has(filter.id)}
            onPress={() => onFilterChange(filter.id)}
          />
        ))}
        <View style={styles.divider} />
        <TouchableOpacity
          style={[styles.filterButton, styles.slopButton, slopFree && styles.slopButtonActive]}
          onPress={() => onSlopFreeChange(!slopFree)}
          activeOpacity={0.7}>
          <Text style={[styles.filterText, styles.slopText, slopFree && styles.slopTextActive]}>
            {slopFree ? 'SLOP FREE' : 'WITH SLOP'}
          </Text>
        </TouchableOpacity>
      </ScrollView>
    </View>
  );
}

function FilterButton({label, isSelected, onPress}) {
  return (
    <TouchableOpacity
      style={[styles.filterButton, isSelected && styles.filterButtonSelected]}
      onPress={onPress}
      activeOpacity={0.7}>
      <Text
        style={[
          styles.filterText,
          isSelected && styles.filterTextSelected,
        ]}>
        {label}
      </Text>
    </TouchableOpacity>
  );
}

const styles = StyleSheet.create({
  container: {
    backgroundColor: Colors.background,
    paddingVertical: Spacing.sm,
    borderBottomWidth: 1,
    borderBottomColor: Colors.backgroundSecondary,
  },
  scrollContent: {
    paddingHorizontal: Spacing.screenPadding,
    gap: Spacing.sm,
    alignItems: 'center',
  },
  filterButton: {
    paddingVertical: Spacing.sm,
    paddingHorizontal: Spacing.md,
    borderRadius: 20,
    backgroundColor: Colors.backgroundSecondary,
    borderWidth: 1,
    borderColor: Colors.backgroundTertiary,
  },
  filterButtonSelected: {
    backgroundColor: Colors.primary,
    borderColor: Colors.primary,
  },
  filterText: {
    color: Colors.textSecondary,
    fontSize: Typography.caption + 1,
    fontWeight: '500',
  },
  filterTextSelected: {
    color: Colors.featuredBadgeText,
    fontWeight: '600',
  },
  divider: {
    width: 1,
    height: 20,
    backgroundColor: 'rgba(255,255,255,0.15)',
    marginHorizontal: 4,
  },
  slopButton: {
    borderColor: 'rgba(255,100,100,0.4)',
    backgroundColor: 'transparent',
  },
  slopButtonActive: {
    backgroundColor: 'rgba(255,68,68,0.15)',
    borderColor: '#ff4444',
  },
  slopText: {
    color: 'rgba(255,180,180,0.8)',
    fontWeight: '600',
    fontSize: Typography.caption,
    letterSpacing: 0.5,
  },
  slopTextActive: {
    color: '#ff8888',
  },
});
