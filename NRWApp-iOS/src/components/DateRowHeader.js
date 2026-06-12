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
  'fest': {day: 'FEST', rest: 'NOW SCREENING', color: '#f59e0b'},
  'highlights': {day: 'HIGHLIGHTS', rest: '', color: '#dc143c'},
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

  return (
    <View style={[styles.row, {borderColor: color, shadowColor: color}]}>
      <Text style={[styles.day, {color, textShadowColor: color}]}>{day}</Text>
      {rest ? <Text style={styles.rest}>{rest}</Text> : null}
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
});
