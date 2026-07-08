/**
 * New Release Wall - Filter Bar Component
 * Mirrors the approved mobile layout: a toggle row (SLOP FILTER · SELECTS · FESTS
 * · PRE-ORDER, canonical web order) above a row with the GENRE control + search.
 */

import React from 'react';
import {View, Text, StyleSheet, TextInput, TouchableOpacity, Modal} from 'react-native';
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

const SLOP_STATES = ['all', 'free', 'only'];
const SLOP_LABELS = {all: 'SLOP FILTER', free: 'SLOP FREE', only: 'SLOP ONLY'};

const GOLD = '#FFD700';
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

// 3-state slop slider (all → free → only), matching mobile
function SlopToggle({mode, onPress}) {
  const isAll = mode === 'all';
  const isOnly = mode === 'only';
  const color = isOnly ? ORANGE : TEAL;
  const thumbX = mode === 'free' ? 0 : isAll ? 5 : 11;
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
  const [genreSheet, setGenreSheet] = React.useState(false);
  const activeGenreId = activeFilters.size ? [...activeFilters][0] : null;
  const activeGenre = FILTERS.find(f => f.id === activeGenreId);
  return (
    <View style={styles.container}>
      {/* Toggle row — all four fit without scrolling; canonical web order:
          SLOP FILTER · SELECTS · FESTS · PRE-ORDER */}
      <View style={styles.toggleRow}>
        <SlopToggle mode={slopMode} onPress={() => onSlopModeChange(SLOP_STATES[(SLOP_STATES.indexOf(slopMode) + 1) % 3])} />
        <Toggle label="SELECTS" active={showHighlightsOnly} color={TEAL} onPress={() => onShowHighlightsChange(!showHighlightsOnly)} />
        <Toggle label="FESTS" active={!hideFest} color={GOLD} onPress={() => onHideFestChange(!hideFest)} />
        <Toggle label="PRE-ORDER" active={showPreorders} color={PURPLE} onPress={() => onShowPreordersChange(!showPreorders)} />
      </View>

      {/* Row 2: quiet GENRE control (opens a bottom sheet) + inline search */}
      <View style={styles.row2}>
        <TouchableOpacity
          style={[styles.genreControl, activeGenre && styles.genreControlActive]}
          onPress={() => setGenreSheet(true)}
          activeOpacity={0.8}>
          <Text style={[styles.genreText, activeGenre && styles.genreTextActive]} numberOfLines={1}>
            {activeGenre ? activeGenre.label.toUpperCase() : 'GENRE'}
          </Text>
          <Text style={[styles.genreCaret, activeGenre && styles.genreTextActive]}>▾</Text>
        </TouchableOpacity>
        <View style={styles.searchWrap}>
          <TextInput
            style={styles.searchInput}
            placeholder="Search..."
            placeholderTextColor={Colors.textMuted}
            value={searchQuery}
            onChangeText={onSearchChange}
            returnKeyType="search"
            autoCorrect={false}
            autoCapitalize="none"
          />
        </View>
      </View>

      {/* GENRE bottom sheet */}
      <Modal
        visible={genreSheet}
        transparent
        animationType="slide"
        onRequestClose={() => setGenreSheet(false)}>
        <TouchableOpacity style={styles.sheetBackdrop} activeOpacity={1} onPress={() => setGenreSheet(false)}>
          <TouchableOpacity style={styles.sheet} activeOpacity={1} onPress={() => {}}>
            <View style={styles.sheetHandle} />
            <View style={styles.sheetHead}>
              <Text style={styles.sheetHeadText}>FILTER BY GENRE</Text>
              <TouchableOpacity onPress={() => { if (activeGenreId) onFilterChange(activeGenreId); }}>
                <Text style={styles.sheetClear}>Clear</Text>
              </TouchableOpacity>
            </View>
            <View style={styles.sheetChips}>
              {FILTERS.map(filter => {
                const sel = activeFilters.has(filter.id);
                return (
                  <TouchableOpacity
                    key={filter.id}
                    style={[styles.pill, sel && styles.pillSelected]}
                    onPress={() => { onFilterChange(filter.id); setGenreSheet(false); }}
                    activeOpacity={0.7}>
                    <Text style={[styles.pillText, sel && styles.pillTextSelected]}>{filter.label}</Text>
                  </TouchableOpacity>
                );
              })}
            </View>
            <TouchableOpacity style={styles.sheetDone} onPress={() => setGenreSheet(false)} activeOpacity={0.85}>
              <Text style={styles.sheetDoneText}>Done</Text>
            </TouchableOpacity>
          </TouchableOpacity>
        </TouchableOpacity>
      </Modal>
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
  // toggle row — all four fit across the width
  toggleRow: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    paddingHorizontal: Spacing.sm,
    paddingVertical: Spacing.xs,
  },
  toggleWrap: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 5,
  },
  track: {
    width: 28,
    height: 17,
    borderRadius: 9,
    backgroundColor: '#1a1a1a',
    borderWidth: 1,
    borderColor: 'rgba(0,212,170,0.45)',
    justifyContent: 'center',
  },
  thumb: {
    position: 'absolute',
    left: 2,
    width: 11,
    height: 11,
    borderRadius: 6,
    backgroundColor: 'rgba(0,212,170,0.55)',
  },
  thumbOn: {
    transform: [{translateX: 11}],
    backgroundColor: '#fff',
  },
  toggleLabel: {
    fontSize: 9,
    fontWeight: '700',
    letterSpacing: 0.3,
    color: 'rgba(0,212,170,0.6)',
  },
  // row 2: GENRE control + inline search
  row2: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: Spacing.sm,
    paddingHorizontal: Spacing.screenPadding,
    paddingTop: Spacing.sm,
  },
  genreControl: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 5,
    paddingVertical: 6,
    paddingHorizontal: 12,
    borderRadius: 20,
    borderWidth: 1,
    borderColor: 'rgba(0,212,170,0.35)',
    backgroundColor: 'transparent',
  },
  genreControlActive: {
    borderColor: 'rgba(0,212,170,0.55)',
  },
  genreText: {
    fontSize: 10,
    fontWeight: '700',
    letterSpacing: 0.6,
    color: 'rgba(0,212,170,0.75)',
  },
  genreTextActive: {
    color: '#00d4aa',
  },
  genreCaret: {
    fontSize: 8,
    color: 'rgba(0,212,170,0.75)',
  },
  // genre chips (reused inside the bottom sheet)
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
  // search — inline beside the GENRE control
  searchWrap: {
    flex: 1,
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
  // GENRE bottom sheet
  sheetBackdrop: {
    flex: 1,
    backgroundColor: 'rgba(0,0,0,0.6)',
    justifyContent: 'flex-end',
  },
  sheet: {
    backgroundColor: '#14141f',
    borderTopLeftRadius: 18,
    borderTopRightRadius: 18,
    borderWidth: 1,
    borderBottomWidth: 0,
    borderColor: 'rgba(255,255,255,0.12)',
    paddingHorizontal: 16,
    paddingTop: 8,
    paddingBottom: 34,
  },
  sheetHandle: {
    width: 38,
    height: 4,
    borderRadius: 2,
    backgroundColor: 'rgba(255,255,255,0.25)',
    alignSelf: 'center',
    marginTop: 6,
    marginBottom: 12,
  },
  sheetHead: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: 12,
  },
  sheetHeadText: {
    color: Colors.textMuted,
    fontSize: 11,
    fontWeight: '700',
    letterSpacing: 1,
  },
  sheetClear: {
    color: '#00d4aa',
    fontSize: 13,
    fontWeight: '600',
  },
  sheetChips: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: 8,
  },
  sheetDone: {
    marginTop: 16,
    paddingVertical: 11,
    borderRadius: 20,
    backgroundColor: '#00d4aa',
    alignItems: 'center',
  },
  sheetDoneText: {
    color: '#000',
    fontWeight: '700',
    letterSpacing: 1,
    fontSize: 14,
  },
});
