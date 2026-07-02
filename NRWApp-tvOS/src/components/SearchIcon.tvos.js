/**
 * SearchIcon — real magnifying-glass icon (replaces the old ⌕ unicode glyph).
 * Vector (react-native-svg, pod-linked) so it stays crisp at any size.
 */

import React from 'react';
import Svg, { Circle, Line } from 'react-native-svg';

const SearchIcon = ({ size = 24, color = '#00d4aa', strokeWidth = 1.8 }) => (
  <Svg width={size} height={size} viewBox="0 0 20 20" fill="none">
    <Circle cx="8.5" cy="8.5" r="5.5" stroke={color} strokeWidth={strokeWidth} />
    <Line
      x1="12.8"
      y1="12.8"
      x2="18"
      y2="18"
      stroke={color}
      strokeWidth={strokeWidth}
      strokeLinecap="round"
    />
  </Svg>
);

export default SearchIcon;
