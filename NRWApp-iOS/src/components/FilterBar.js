/**
 * New Release Wall - Filter Bar Component
 * Mirrors the approved mobile layout: a toggle row (FESTS · PRE-ORDER · SLOP FREE
 * · SELECTS) above a row of genre pills + search.
 */

import React from 'react';
import {View, Text, StyleSheet, ScrollView, TextInput, TouchableOpacity} from 'react-native';
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

const AMBER = '#f59e0b';
const PURPLE = '#7c3aed';
const TEAL = '#00d4aa';
const ORANGE = '#ff9500';

// Slider toggle matching the mobile track+thumb (2-state)
function Toggle({label, active, color, onPress}) {
  return (
    <TouchableOpacity style={styles.toggleWrap} onPress={onPress} activeOpacity={0.8}>
      <View style={[styles.track, active && {backgroundColor: color, borderColor: color}]}>
        <View style={[styles.thumb, active && styles.thumbOn]} />
      </View>
      <Text style={[styles.toggleLabel, active && {color}]} numberOfLines={1}>{label}</Text>
    </TouchableOpacity>
  );
}

// 3-state slop slider (free → all → only), matching mobile
function SlopToggle({mode, onPress}) {
  const isAll = mode === 'all';
  const isOnly = mode === 'only';
  const color = isOnly ? ORANGE : TEAL;
  const thumbX = mode === 'free' ? 0 : isAll ? 8 : 16;
  return (
    <TouchableOpacity style={styles.toggleWrap} onPress={onPress} activeOpacity={0.8}>
      <View style={[styles.track, {borderColor: color}, !isAll && {backgroundColor: color}]}>
        <View style={[styles.thumb, {transform: [{translateX: thumbX}], backgroundColor: isAll ? color : '#fff'}]} />
      </View>
      <Text style={[styles.toggleLabel, {color}]} numberOfLines={1}>{SLOP_LABELS[mode]}</Text>
    </TouchableOpacity>
  );
}

export default function FilterBar({
  activeFilters, onFilterChange,
  slopMode, onSlopModeChange,
  hideFest, onHideFestChange,
  showPreorders, onShowPreordersChange,
  showHighlightsOnly, onShowHighlightsChange,
  searchQuery, onSearchChange,
}) {
  return (
    <View style={styles.container}>
      {/* Toggle row */}
      <View style={styles.toggleRow}>
        <Toggle label="FESTS" active={!hideFest} color={AMBER} onPress={() => onHideFestChange(!hideFest)} />
        <View style={styles.toggleDivider} />
        <Toggle label="PRE-ORDER" active={showPreorders} color={PURPLE} onPress={() => onShowPreordersChange(!showPreorders)} />
        <View style={styles.toggleDivider} />
        <SlopToggle mode={slopMode} onPress={() => onSlopModeChange(SLOP_STATES[(SLOP_STATES.indexOf(slopMode) + 1) % 3])} />
        <View style={styles.toggleDivider} />
        <Toggle label="SELECTS" active={showHighlightsOnly} color={TEAL} onPress={() => onShowHighlightsChange(!showHighlightsOnly)} />
      </View>

      {/* Genre pills */}
      <ScrollView
        horizontal
        showsHorizontalScrollIndicator={false}
        contentContainerStyle={styles.pillRow}>
        {FILTERS.map(filter => {
          const sel = activeFilters.has(filter.id);
          return (
            <TouchableOpacity
              key={filter.id}
              style={[styles.pill, sel && styles.pillSelected]}
              onPress={() => onFilterChange(filter.id)}
              activeOpacity={0.7}>
              <Text style={[styles.pillText, sel && styles.pillTextSelected]}>{filter.label}</Text>
            </TouchableOpacity>
          );
        })}
      </ScrollView>

      {/* Search */}
      <View style={styles.searchWrap}>
        <TextInput
          style={styles.searchInput}
          placeholder="Search title, director, genre..."
          placeholderTextColor={Colors.textMuted}
          value={searchQuery}
          onChangeText={onSearchChange}
          returnKeyType="search"
          autoCorrect={false}
          autoCapitalize="none"
        />
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    backgroundColor: Colors.background,
    paddingTop: Spacing.xs,
    paddingBottom: Spacing.sm,
    borderBottomWidth: 1,
    borderBottomColor: Colors.backgroundSecondary,
  },
  // toggle row
  toggleRow: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    paddingHorizontal: Spacing.screenPadding,
    paddingVertical: Spacing.xs,
  },
  toggleDivider: {
    width: 1,
    height: 18,
    backgroundColor: 'rgba(255,255,255,0.15)',
  },
  toggleWrap: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 6,
  },
  track: {
    width: 34,
    height: 20,
    borderRadius: 10,
    backgroundColor: '#1a1a1a',
    borderWidth: 1,
    borderColor: 'rgba(0,212,170,0.45)',
    justifyContent: 'center',
  },
  thumb: {
    position: 'absolute',
    left: 2,
    width: 14,
    height: 14,
    borderRadius: 7,
    backgroundColor: 'rgba(0,212,170,0.55)',
  },
  thumbOn: {
    transform: [{translateX: 16}],
    backgroundColor: '#fff',
  },
  toggleLabel: {
    fontSize: 10,
    fontWeight: '700',
    letterSpacing: 0.6,
    color: 'rgba(0,212,170,0.6)',
  },
  // genre pills
  pillRow: {
    paddingHorizontal: Spacing.screenPadding,
    paddingTop: Spacing.sm,
    gap: Spacing.sm,
    alignItems: 'center',
  },
  pill: {
    paddingVertical: 6,
    paddingHorizontal: 14,
    borderRadius: 20,
    backgroundColor: Colors.backgroundSecondary,
    borderWidth: 1,
    borderColor: Colors.backgroundTertiary,
  },
  pillSelected: {
    backgroundColor: Colors.primary,
    borderColor: Colors.primary,
  },
  pillText: {
    color: Colors.textSecondary,
    fontSize: Typography.caption + 1,
    fontWeight: '500',
  },
  pillTextSelected: {
    color: Colors.featuredBadgeText || '#06231d',
    fontWeight: '700',
  },
  // search
  searchWrap: {
    paddingHorizontal: Spacing.screenPadding,
    paddingTop: Spacing.sm,
  },
  searchInput: {
    backgroundColor: Colors.backgroundSecondary,
    borderRadius: 20,
    paddingVertical: 8,
    paddingHorizontal: 14,
    color: Colors.textPrimary,
    fontSize: Typography.body,
    borderWidth: 1,
    borderColor: Colors.backgroundTertiary,
  },
});
