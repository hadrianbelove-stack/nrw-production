/**
 * New Release Wall - Date Divider Card (iOS)
 * Matches mobile web design: teal bar + day/number/month + cascading chevrons
 */

import React from 'react';
import {View, Text, StyleSheet} from 'react-native';
import {Colors, Spacing} from '../constants/colors';

export default function DateDividerCard({dateString, style}) {
  const isPreOrder = dateString === 'pre-order';

  let weekday = '';
  let day = '';
  let month = '';

  if (!isPreOrder) {
    const d = new Date(dateString + 'T12:00:00');
    weekday = d.toLocaleDateString('en', {weekday: 'short'}).toUpperCase();
    day = String(d.getDate());
    month = d.toLocaleDateString('en', {month: 'short'}).toUpperCase();
  }

  const barColor = isPreOrder ? '#7c3aed' : Colors.primary;
  const accentColor = isPreOrder ? '#7c3aed' : Colors.primary;

  return (
    <View style={[styles.container, style]}>
      {/* Top bar */}
      <View style={[styles.bar, {backgroundColor: barColor}]}>
        <Text style={styles.barText}>
          {isPreOrder ? 'PRE-ORDER' : weekday}
        </Text>
      </View>

      {/* Body */}
      <View style={styles.body}>
        <Text style={[styles.number, isPreOrder && styles.numberSmall, {color: isPreOrder ? accentColor : '#fff'}]}>
          {isPreOrder ? 'SOON' : day}
        </Text>
        {!isPreOrder && (
          <Text style={styles.month}>{month}</Text>
        )}
        {/* Cascading chevrons */}
        <View style={styles.chevrons}>
          {[0.9, 0.7, 0.5, 0.3, 0.15].map((opacity, i) => (
            <Text key={i} style={[styles.chevron, {color: accentColor, opacity}]}>
              {'\u203A'}
            </Text>
          ))}
        </View>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    aspectRatio: 2 / 3,
    borderRadius: 8,
    overflow: 'hidden',
    backgroundColor: '#0a0a0a',
  },
  bar: {
    paddingVertical: 4,
    paddingHorizontal: 8,
  },
  barText: {
    fontSize: 9,
    fontWeight: '800',
    color: '#000',
    letterSpacing: 0.5,
  },
  body: {
    flex: 1,
    paddingLeft: 8,
    justifyContent: 'center',
  },
  number: {
    fontSize: 42,
    fontWeight: '800',
    lineHeight: 42,
  },
  numberSmall: {
    fontSize: 20,
  },
  month: {
    fontSize: 10,
    color: '#888',
    letterSpacing: 1,
    marginTop: 2,
  },
  chevrons: {
    flexDirection: 'row',
    marginTop: 4,
  },
  chevron: {
    fontSize: 28,
    fontWeight: '800',
    lineHeight: 28,
  },
});
