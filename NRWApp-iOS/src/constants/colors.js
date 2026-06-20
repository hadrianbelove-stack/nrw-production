/**
 * New Release Wall - Brand Colors for iOS
 */

export const Colors = {
  // Primary brand colors
  primary: '#00d4aa',        // Teal accent (NRW brand)
  primaryDark: '#00a88a',    // Darker teal for pressed states

  // Background colors
  background: '#0a0a0a',     // Dark background
  backgroundSecondary: '#1a1a1a', // Card backgrounds
  backgroundTertiary: '#2a2a2a',  // Elevated surfaces

  // Text colors
  textPrimary: '#ffffff',    // Primary text
  textSecondary: '#b0b0b0',  // Secondary text
  textMuted: '#707070',      // Muted/disabled text

  // Accent colors
  orange: '#ff9500',         // Purchase buttons (Amazon)
  teal: '#00d4aa',           // Streaming buttons
  red: '#ff3b30',            // Error states, Rotten Tomatoes
  green: '#34c759',          // Success states, fresh RT score

  // Service-specific colors
  amazonOrange: '#ff9900',
  appleTVBlack: '#000000',
  netflixRed: '#e50914',

  // Staff Pick badge (Select) — teal brand
  staffPick: '#00d4aa',
  staffPickText: '#00ffbb',

  // Restoration badge
  restoration: '#C8A951',
  restorationText: '#000000',
};

export const Typography = {
  title: 28,
  subtitle: 20,
  body: 16,
  caption: 12,
  button: 16,
};

export const Spacing = {
  xs: 4,
  sm: 8,
  md: 16,
  lg: 24,
  xl: 32,
  cardGap: 12,
  screenPadding: 16,
};

export const Dimensions = {
  cardWidth: 160,
  cardHeight: 240,
  posterAspectRatio: 2 / 3,
};

export default {
  Colors,
  Typography,
  Spacing,
  Dimensions,
};
