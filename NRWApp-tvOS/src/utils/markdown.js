import React from 'react';
import {Text} from 'react-native';

// Render a tiny markdown subset (**bold**, *italic*, [text](url)) into styled <Text> spans.
// Returns an array of <Text> that inherits the parent <Text>'s base style.
// Links [text](url) are stripped to plain text — URLs discarded (not navigable on tvOS/iOS).
// Canonical spec: docs/STYLE_GUIDE.md "Synopsis / Capsule Text Formatting".
// NOTE: keep byte-identical with the NRWApp-iOS twin (separate npm projects).
export const renderMarkdownSpans = (text) => {
  if (!text) return null;
  // Strip markdown links first so **[Name](url)** and *[Film](url)* render correctly
  const stripped = text.replace(/\[([^\]]+)\]\([^)]+\)/g, '$1');
  const regex = /\*\*([^*]+)\*\*|\*([^*]+)\*/g;
  const spans = [];
  let lastIndex = 0;
  let key = 0;
  let m;
  while ((m = regex.exec(stripped)) !== null) {
    if (m.index > lastIndex) {
      spans.push(<Text key={key++}>{stripped.slice(lastIndex, m.index)}</Text>);
    }
    if (m[1] !== undefined) {
      spans.push(<Text key={key++} style={{fontWeight: '700'}}>{m[1]}</Text>);
    } else {
      spans.push(<Text key={key++} style={{fontStyle: 'italic'}}>{m[2]}</Text>);
    }
    lastIndex = regex.lastIndex;
  }
  if (lastIndex < stripped.length) {
    spans.push(<Text key={key++}>{stripped.slice(lastIndex)}</Text>);
  }
  return spans;
};
