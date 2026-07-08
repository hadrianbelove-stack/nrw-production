/**
 * New Release Wall - tvOS On-Screen Search Keyboard
 * Custom d-pad key grid (ports the Roku app's two-mode SearchScreen pattern —
 * NRWApp-Roku/components/screens/SearchScreen.brs). Exists because the system
 * tvOS keyboard blurs everything behind it until the query is committed; this
 * grid leaves the live results visible beside it at all times.
 *
 * Pure input surface: emits characters/actions upward, owns no query state.
 * 10-foot floors: key glyphs 28pt, control labels 24pt (spec: keys >= 24pt).
 * Focus styling: solid teal key + dark glyph — brand-consistent with the teal
 * FOCUS_STYLES treatments used across the app.
 */

import React, { useState, useCallback } from 'react';
import { View, Text, StyleSheet, TouchableOpacity } from 'react-native';
import { Colors } from '../constants/colors';

// 6x6 letters+digits, then a controls row. Alphabetical grid reads fastest
// on a d-pad (Roku/Netflix convention).
const KEY_ROWS = [
  ['A', 'B', 'C', 'D', 'E', 'F'],
  ['G', 'H', 'I', 'J', 'K', 'L'],
  ['M', 'N', 'O', 'P', 'Q', 'R'],
  ['S', 'T', 'U', 'V', 'W', 'X'],
  ['Y', 'Z', '0', '1', '2', '3'],
  ['4', '5', '6', '7', '8', '9'],
];

const Key = ({ label, wide, onPress, onFocus, hasTVPreferredFocus, accessibilityLabel, testID }) => {
  const [focused, setFocused] = useState(false);

  const handleFocus = useCallback(() => {
    setFocused(true);
    if (onFocus) onFocus();
  }, [onFocus]);

  const handleBlur = useCallback(() => setFocused(false), []);

  return (
    <TouchableOpacity
      style={[styles.key, wide && styles.keyWide, focused && styles.keyFocused]}
      activeOpacity={1}
      onPress={onPress}
      onFocus={handleFocus}
      onBlur={handleBlur}
      hasTVPreferredFocus={hasTVPreferredFocus}
      accessible={true}
      accessibilityRole="button"
      accessibilityLabel={accessibilityLabel || label}
      testID={testID}
    >
      <Text style={[wide ? styles.keyLabelWide : styles.keyLabel, focused && styles.keyLabelFocused]}>
        {label}
      </Text>
    </TouchableOpacity>
  );
};

/**
 * Props:
 *   onChar(ch)      — append a character (SPACE emits ' ')
 *   onDelete()      — backspace
 *   onClear()       — clear the whole query
 *   onKeyFocus()    — any key gained focus (parent flips to KEYBOARD mode)
 *   preferredFocus  — one-shot: seed tvOS focus onto the 'A' key (mount + Menu return)
 */
const SearchKeyboard = ({ onChar, onDelete, onClear, onKeyFocus, preferredFocus }) => (
  <View style={styles.keyboard} testID="search-keyboard">
    {KEY_ROWS.map((row, rowIndex) => (
      <View key={`row-${rowIndex}`} style={styles.keyRow}>
        {row.map((ch, colIndex) => (
          <Key
            key={ch}
            label={ch}
            onPress={() => onChar(ch)}
            onFocus={onKeyFocus}
            hasTVPreferredFocus={!!preferredFocus && rowIndex === 0 && colIndex === 0}
            testID={`kbd-key-${ch}`}
          />
        ))}
      </View>
    ))}
    <View style={styles.keyRow}>
      <Key label="SPACE" wide onPress={() => onChar(' ')} onFocus={onKeyFocus} accessibilityLabel="Space" testID="kbd-space" />
      <Key label="DELETE" wide onPress={onDelete} onFocus={onKeyFocus} accessibilityLabel="Delete last character" testID="kbd-delete" />
      <Key label="CLEAR" wide onPress={onClear} onFocus={onKeyFocus} accessibilityLabel="Clear search" testID="kbd-clear" />
    </View>
  </View>
);

const KEY_GAP = 10;

const styles = StyleSheet.create({
  // 6 keys * 76 + 5 gaps * 10 = 506 wide (parent pane is sized to match)
  keyboard: {
    width: 506,
  },
  keyRow: {
    flexDirection: 'row',
    gap: KEY_GAP,
    marginBottom: KEY_GAP,
  },
  key: {
    width: 76,
    height: 72,
    borderRadius: 10,
    backgroundColor: 'rgba(255, 255, 255, 0.08)',
    borderWidth: 2,
    borderColor: 'transparent',
    justifyContent: 'center',
    alignItems: 'center',
  },
  // Controls row: three equal keys spanning the grid width
  keyWide: {
    flex: 1,
    width: undefined,
  },
  keyFocused: {
    backgroundColor: Colors.primary,
    borderColor: Colors.focusBorderHighlight,
  },
  keyLabel: {
    color: Colors.textPrimary,
    fontSize: 28,
    fontWeight: '700',
  },
  keyLabelWide: {
    color: Colors.textSecondary,
    fontSize: 24,
    fontWeight: '700',
    letterSpacing: 1,
  },
  keyLabelFocused: {
    color: Colors.staffPickText,
  },
});

export default SearchKeyboard;
