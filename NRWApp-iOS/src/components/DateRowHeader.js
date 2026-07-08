/**
 * New Release Wall - Date Row Strip (iOS)
 * Neon sticky banner between date groups: glowing top/bottom borders,
 * colored day name + white date, centered. Sticks while its day scrolls.
 */

import React from 'react';
import {View, Text, StyleSheet} from 'react-native';
import {Colors} from '../constants/colors';

const SECTION_STRIPS = {
  'pre-order': {day: 'PRE-ORDER', rest: 'COMING SOON', color: '#7c3aed'},
  'fest-active': {day: 'FESTS', rest: 'AVAILABLE NOW', color: '#FFD700'},
  'fest-upcoming': {day: 'FESTS', rest: 'COMING SOON', color: '#b9952e'},
  'highlights': {day: 'SELECTS', rest: 'OF NOTE', color: '#00d4aa'},
  'slop': {day: 'SLOP', rest: 'THE CONTENT RIVER', color: '#ff9500'},
};

export default function DateRowHeader({dateString, stripColor}) {
  const section = SECTION_STRIPS[dateString];

  let day, rest, color;
  if (section) {
    ({day, rest, color} = section);
  } else {
    const d = new Date(dateString + 'T12:00:00');
    day = d.toLocaleDateString('en', {weekday: 'short'}).toUpperCase();
    rest = `${d.toLocaleDateString('en', {month: 'short'})} ${d.getDate()}`.toUpperCase();
    color = stripColor || Colors.primary;
  }

  const isSection = !!section;

  return (
    <View style={[styles.row, isSection && styles.rowSection, {borderColor: color, shadowColor: color}]}>
      <Text style={[styles.day, isSection && styles.daySection, {color, textShadowColor: color}]}>{day}</Text>
      {rest ? <Text style={[styles.rest, isSection && styles.restSection]}>{rest}</Text> : null}
    </View>
  );
}

const styles = StyleSheet.create({
  row: {
    flexDirection: 'row',
    justifyContent: 'center',
    alignItems: 'baseline',
    gap: 10,
    backgroundColor: 'rgba(8,8,12,0.96)',
    borderTopWidth: 1.5,
    borderBottomWidth: 1.5,
    borderRadius: 4,
    paddingVertical: 9,
    paddingHorizontal: 10,
    marginTop: 8,
    shadowOpacity: 0.55,
    shadowRadius: 12,
    shadowOffset: {width: 0, height: 0},
  },
  day: {
    fontSize: 15,
    fontWeight: '900',
    letterSpacing: 4,
    textTransform: 'uppercase',
    textShadowRadius: 8,
    textShadowOffset: {width: 0, height: 0},
  },
  rest: {
    fontSize: 15,
    fontWeight: '500',
    letterSpacing: 4,
    color: '#fff',
    textTransform: 'uppercase',
  },
  // Section banner (SLOP / SELECTS / FESTS / PRE-ORDER) — ~2x the date dividers
  rowSection: {
    borderTopWidth: 3,
    borderBottomWidth: 3,
    borderRadius: 6,
    paddingVertical: 18,
    shadowOpacity: 0.7,
    shadowRadius: 20,
  },
  daySection: {fontSize: 30},
  restSection: {fontSize: 30, fontWeight: '400'},
});
