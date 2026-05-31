/**
 * New Release Wall - Filter Bar Component
 * Horizontal scrollable filter buttons
 */

import React from 'react';
import {View, Text, StyleSheet, ScrollView, TouchableOpacity} from 'react-native';
import {Colors, Typography, Spacing} from '../constants/colors';

const FILTERS = [
  {id: 'staff-picks', label: 'Picks'},
  {id: 'indie', label: 'Indie'},
  {id: 'horror', label: 'Horror'},
  {id: 'action', label: 'Action'},
  {id: 'comedy', label: 'Comedy'},
  {id: 'family', label: 'Family'},
  {id: 'foreign', label: 'Foreign'},
  {id: 'documentary', label: 'Docs'},
  {id: 'restorations', label: 'Reissues'},
];

export default function FilterBar({activeFilters, onFilterChange, slopFree, onSlopFreeChange, hideFest, onHideFestChange, showPreorders, onShowPreordersChange}) {
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
        <View style={styles.divider} />
        <TouchableOpacity
          style={[styles.filterButton, styles.slopButton, hideFest && styles.slopButtonActive]}
          onPress={() => onHideFestChange(!hideFest)}
          activeOpacity={0.7}>
          <Text style={[styles.filterText, styles.slopText, hideFest && styles.slopTextActive]}>
            {hideFest ? 'NO FEST' : 'WITH FEST'}
          </Text>
        </TouchableOpacity>
        <View style={styles.divider} />
        <TouchableOpacity
          style={[styles.filterButton, styles.slopButton, showPreorders && styles.slopButtonActive]}
          onPress={() => onShowPreordersChange(!showPreorders)}
          activeOpacity={0.7}>
          <Text style={[styles.filterText, styles.slopText, showPreorders && styles.slopTextActive]}>
            {showPreorders ? 'PRE-ORDERS' : 'NO PRE-ORDERS'}
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
    borderColor: 'rgba(0,212,170,0.3)',
    backgroundColor: 'transparent',
  },
  slopButtonActive: {
    backgroundColor: 'rgba(0,212,170,0.15)',
    borderColor: '#00d4aa',
  },
  slopText: {
    color: 'rgba(0,212,170,0.45)',
    fontWeight: '600',
    fontSize: Typography.caption,
    letterSpacing: 0.5,
  },
  slopTextActive: {
    color: '#00d4aa',
  },
});
