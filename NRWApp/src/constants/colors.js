/**
 * New Release Wall - Shared Brand Colors
 * Used across iOS and tvOS platforms
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

  // Focus states (tvOS)
  focusGlow: 'rgba(0, 212, 170, 0.5)',  // Teal glow for focused items
  focusBorder: '#00d4aa',

  // Gradients
  gradientStart: 'rgba(0, 0, 0, 0)',
  gradientEnd: 'rgba(0, 0, 0, 0.9)',

  // Featured badge
  featuredBadge: '#00d4aa',
  featuredBadgeText: '#000000',
};

export const Typography = {
  // tvOS optimized font sizes (10-foot viewing)
  tvos: {
    title: 48,
    subtitle: 32,
    body: 24,
    caption: 18,
    button: 22,
  },
  // iOS font sizes
  ios: {
    title: 28,
    subtitle: 20,
    body: 16,
    caption: 12,
    button: 16,
  },
};

export const Spacing = {
  // tvOS spacing (larger for TV screens)
  tvos: {
    xs: 8,
    sm: 16,
    md: 24,
    lg: 40,
    xl: 60,
    cardGap: 20,
    shelfGap: 40,
    screenPadding: 60,
  },
  // iOS spacing
  ios: {
    xs: 4,
    sm: 8,
    md: 16,
    lg: 24,
    xl: 32,
    cardGap: 12,
    screenPadding: 16,
  },
};

export const Dimensions = {
  // tvOS card dimensions (20% smaller)
  tvos: {
    cardWidth: 224,
    cardHeight: 336,
    featuredCardWidth: 224,
    featuredCardHeight: 336,
    posterAspectRatio: 2 / 3,
  },
  // iOS card dimensions
  ios: {
    cardWidth: 160,
    cardHeight: 240,
    posterAspectRatio: 2 / 3,
  },
};

export default {
  Colors,
  Typography,
  Spacing,
  Dimensions,
};
