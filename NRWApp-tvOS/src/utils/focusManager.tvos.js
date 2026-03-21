/**
 * New Release Wall - tvOS Focus Management Utilities
 * Handles focus engine, remote control events, and navigation
 */

import { useEffect, useRef, useCallback, useState } from 'react';
import {
  TVEventHandler,
  findNodeHandle,
  AccessibilityInfo,
  Platform,
} from 'react-native';

// Event types from Siri Remote
// Note: On newer remotes the "Menu" button is labeled "Back" (<) but both
// fire as 'menu' in React Native tvOS. BACK is an alias for semantic clarity.
export const TV_EVENTS = {
  SELECT: 'select',
  PLAY_PAUSE: 'playPause',
  MENU: 'menu',
  BACK: 'menu',  // Alias — same event, clearer intent for dismiss/go-back
  UP: 'up',
  DOWN: 'down',
  LEFT: 'left',
  RIGHT: 'right',
  LONG_SELECT: 'longSelect',
  SWIPE_UP: 'swipeUp',
  SWIPE_DOWN: 'swipeDown',
  SWIPE_LEFT: 'swipeLeft',
  SWIPE_RIGHT: 'swipeRight',
};

/**
 * Hook to handle TV remote control events
 * @param {Object} handlers - Object with event handlers for each event type
 */
export function useTVEventHandler(handlers) {
  const handlersRef = useRef(handlers);
  handlersRef.current = handlers;

  useEffect(() => {
    if (Platform.OS !== 'ios' || !Platform.isTV) {
      return;
    }

    const handler = new TVEventHandler();

    handler.enable(null, (cmp, evt) => {
      const eventType = evt?.eventType;

      if (eventType && handlersRef.current[eventType]) {
        handlersRef.current[eventType](evt);
      }
    });

    return () => {
      handler.disable();
    };
  }, []);
}

/**
 * Hook to manage focus state for a component
 * @returns {Object} - { isFocused, onFocus, onBlur, focusRef }
 */
export function useFocusState() {
  const [isFocused, setIsFocused] = useState(false);
  const focusRef = useRef(null);

  const onFocus = useCallback(() => {
    setIsFocused(true);
  }, []);

  const onBlur = useCallback(() => {
    setIsFocused(false);
  }, []);

  return {
    isFocused,
    onFocus,
    onBlur,
    focusRef,
  };
}

/**
 * Request focus on a specific component
 * @param {Object} ref - React ref to the component
 */
export function requestFocus(ref) {
  if (ref?.current) {
    const nodeHandle = findNodeHandle(ref.current);
    if (nodeHandle) {
      AccessibilityInfo.setAccessibilityFocus(nodeHandle);
    }
  }
}

/**
 * Create focus guide configuration for TVFocusGuideView
 * Used to guide focus between non-adjacent elements
 */
export function createFocusGuide(options = {}) {
  const {
    autoFocus = false,
    trapFocusUp = false,
    trapFocusDown = false,
    trapFocusLeft = false,
    trapFocusRight = false,
    destinations = [],
  } = options;

  return {
    autoFocus,
    trapFocusUp,
    trapFocusDown,
    trapFocusLeft,
    trapFocusRight,
    destinations,
  };
}

/**
 * Check if reduced motion is enabled (accessibility)
 * @returns {Promise<boolean>}
 */
export async function isReducedMotionEnabled() {
  return new Promise(resolve => {
    AccessibilityInfo.isReduceMotionEnabled().then(enabled => {
      resolve(enabled);
    });
  });
}

/**
 * Focus animation configuration
 * Returns appropriate animation values based on accessibility settings
 */
export function getFocusAnimationConfig(isReducedMotion = false) {
  if (isReducedMotion) {
    return {
      scale: 1.0,
      shadowOpacity: 0,
      duration: 0,
    };
  }

  return {
    scale: 1.1,
    shadowOpacity: 0.5,
    duration: 150,
  };
}

/**
 * Parallax properties for movie poster images
 */
export const PARALLAX_PROPERTIES = {
  enabled: true,
  shiftDistanceX: 10,
  shiftDistanceY: 10,
  tiltAngle: 0.05,
  magnification: 1.1,
};

/**
 * Focus style presets for different component types
 */
export const FOCUS_STYLES = {
  movieCard: {
    scale: 1.1,
    shadowColor: '#00d4aa',
    shadowOpacity: 0.5,
    shadowRadius: 20,
    borderWidth: 2,
    borderColor: '#00d4aa',
  },
  button: {
    scale: 1.15,
    shadowColor: '#ffffff',
    shadowOpacity: 0.3,
    shadowRadius: 15,
    borderWidth: 0,
    borderColor: 'transparent',
  },
  menuItem: {
    scale: 1.05,
    shadowColor: '#00d4aa',
    shadowOpacity: 0.4,
    shadowRadius: 10,
    borderWidth: 1,
    borderColor: '#00d4aa',
  },
};

/**
 * Navigation helper - determine next focus target
 * @param {string} direction - 'up', 'down', 'left', 'right'
 * @param {number} currentIndex - Current focused index
 * @param {number} totalItems - Total number of items
 * @param {number} itemsPerRow - Items per row (for grid navigation)
 * @param {boolean} wrap - Whether to wrap around at edges
 */
export function getNextFocusIndex(
  direction,
  currentIndex,
  totalItems,
  itemsPerRow = 1,
  wrap = true
) {
  let nextIndex = currentIndex;

  switch (direction) {
    case 'up':
      nextIndex = currentIndex - itemsPerRow;
      if (nextIndex < 0) {
        nextIndex = wrap ? totalItems + nextIndex : currentIndex;
      }
      break;

    case 'down':
      nextIndex = currentIndex + itemsPerRow;
      if (nextIndex >= totalItems) {
        nextIndex = wrap ? nextIndex - totalItems : currentIndex;
      }
      break;

    case 'left':
      nextIndex = currentIndex - 1;
      if (nextIndex < 0) {
        nextIndex = wrap ? totalItems - 1 : currentIndex;
      }
      break;

    case 'right':
      nextIndex = currentIndex + 1;
      if (nextIndex >= totalItems) {
        nextIndex = wrap ? 0 : currentIndex;
      }
      break;

    default:
      break;
  }

  return nextIndex;
}

/**
 * Debounce function for focus changes
 * Prevents rapid focus changes from overwhelming the UI
 */
export function debounceFocus(func, delay = 100) {
  let timeoutId;

  return function (...args) {
    clearTimeout(timeoutId);
    timeoutId = setTimeout(() => {
      func.apply(this, args);
    }, delay);
  };
}

export default {
  TV_EVENTS,
  useTVEventHandler,
  useFocusState,
  requestFocus,
  createFocusGuide,
  isReducedMotionEnabled,
  getFocusAnimationConfig,
  PARALLAX_PROPERTIES,
  FOCUS_STYLES,
  getNextFocusIndex,
  debounceFocus,
};
