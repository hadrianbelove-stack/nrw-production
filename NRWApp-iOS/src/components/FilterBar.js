/**
 * New Release Wall - Filter Bar Component
 * Horizontal scrollable filter buttons
 */

import React from 'react';
import {View, Text, StyleSheet, ScrollView, TouchableOpacity} from 'react-native';
import {Colors, Typography, Spacing} from '../constants/colors';

const FILTERS = [
  {id: 'indie', label: 'Indie'},
  {id: 'horror', label: 'Horror'},
  {id: 'action', label: 'Action'},
  {id: 'comedy', label: 'Comedy'},
  {id: 'family', label: 'Family'},
  {id: 'thriller', label: 'Thriller'},
  {id: 'foreign', label: 'Foreign'},
  {id: 'documentary', label: 'Docs'},
  {id: 'restorations', label: 'Reissues'},
];

const SLOP_STATES = ['free', 'all', 'only'];
const SLOP_LABELS = {free: 'SLOP FREE', all: 'ALL', only: 'SLOP ONLY'};

export default function FilterBar({activeFilters, onFilterChange, slopMode, onSlopModeChange, hideFest, onHideFestChange, showPreorders, onShowPreordersChange, showHighlightsOnly, onShowHighlightsChange}) {
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
          style={[styles.filterButton, styles.slopButton, !hideFest && styles.festButtonActive]}
          onPress={() => onHideFestChange(!hideFest)}
          activeOpacity={0.7}>
          <Text style={[styles.filterText, styles.slopText, !hideFest && styles.festTextActive]}>
            {hideFest ? 'NO FEST' : 'FESTS'}
          </Text>
        </TouchableOpacity>
        <View style={styles.divider} />
        <TouchableOpacity
          style={[styles.filterButton, styles.slopButton, showPreorders && styles.preorderButtonActive]}
          onPress={() => onShowPreordersChange(!showPreorders)}
          activeOpacity={0.7}>
          <Text style={[styles.filterText, styles.slopText, showPreorders && styles.preorderTextActive]}>
            {showPreorders ? 'PRE-ORDERS' : 'NO PRE-ORDERS'}
          </Text>
        </TouchableOpacity>
        <View style={styles.divider} />
        <TouchableOpacity
          style={[styles.filterButton, styles.slopButton, slopMode !== 'all' && styles.slopButtonActive, slopMode === 'only' && styles.slopButtonOnly]}
          onPress={() => onSlopModeChange(SLOP_STATES[(SLOP_STATES.indexOf(slopMode) + 1) % 3])}
          activeOpacity={0.7}>
          <Text style={[styles.filterText, styles.slopText, slopMode !== 'all' && styles.slopTextActive, slopMode === 'only' && styles.slopTextOnly]}>
            {SLOP_LABELS[slopMode] || 'SLOP FREE'}
          </Text>
        </TouchableOpacity>
        <View style={styles.divider} />
        <TouchableOpacity
          style={[styles.filterButton, styles.slopButton, showHighlightsOnly && styles.selectsButtonActive]}
          onPress={() => onShowHighlightsChange(!showHighlightsOnly)}
          activeOpacity={0.7}>
          <Text style={[styles.filterText, styles.slopText, showHighlightsOnly && styles.selectsTextActive]}>
            SELECTS
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
  slopButtonOnly: {
    backgroundColor: 'rgba(255,149,0,0.15)',
    borderColor: '#ff9500',
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
  slopTextOnly: {
    color: '#ff9500',
  },
  /* View toggles show their identity color when active (matches banners + date strips) */
  selectsButtonActive: {
    backgroundColor: 'rgba(220,20,60,0.15)',
    borderColor: '#dc143c',
  },
  selectsTextActive: {
    color: '#dc143c',
  },
  festButtonActive: {
    backgroundColor: 'rgba(245,158,11,0.15)',
    borderColor: '#f59e0b',
  },
  festTextActive: {
    color: '#f59e0b',
  },
  preorderButtonActive: {
    backgroundColor: 'rgba(124,58,237,0.15)',
    borderColor: '#7c3aed',
  },
  preorderTextActive: {
    color: '#7c3aed',
  },
});
