/**
 * New Release Wall - Filter Bar Component
 * Horizontal scrollable filter buttons
 */

import React from 'react';
import {View, Text, StyleSheet, ScrollView, TouchableOpacity} from 'react-native';
import {Colors, Typography, Spacing} from '../constants/colors';

const FILTERS = [
  {id: 'all', label: 'All'},
  {id: 'staff-picks', label: 'Staff Picks'},
  {id: 'big-time', label: 'Big Time'},
  {id: 'niche', label: 'Indie'},
  {id: 'foreign', label: 'Foreign'},
  {id: 'restorations', label: 'Restorations & Reissues'},
  {id: 'documentary', label: 'Documentary'},
  {id: 'festivals', label: 'Virtual Screenings'},
];

export default function FilterBar({activeFilters, onFilterChange}) {
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
            isSelected={filter.id === 'all' ? activeFilters.size === 0 : activeFilters.has(filter.id)}
            onPress={() => onFilterChange(filter.id)}
          />
        ))}
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
});
