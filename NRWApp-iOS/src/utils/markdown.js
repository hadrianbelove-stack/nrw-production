import React from 'react';
import {Text} from 'react-native';

// Render a tiny markdown subset (**bold**, *italic*) into styled <Text> spans.
// Returns an array of <Text> that inherits the parent <Text>'s base style.
// Canonical spec: docs/STYLE_GUIDE.md "Synopsis / Capsule Text Formatting".
// NOTE: keep byte-identical with the NRWApp-tvOS twin (separate npm projects).
export const renderMarkdownSpans = (text) => {
  if (!text) return null;
  const regex = /\*\*([^*]+)\*\*|\*([^*]+)\*/g;
  const spans = [];
  let lastIndex = 0;
  let key = 0;
  let m;
  while ((m = regex.exec(text)) !== null) {
    if (m.index > lastIndex) {
      spans.push(<Text key={key++}>{text.slice(lastIndex, m.index)}</Text>);
    }
    if (m[1] !== undefined) {
      spans.push(<Text key={key++} style={{fontWeight: '700'}}>{m[1]}</Text>);
    } else {
      spans.push(<Text key={key++} style={{fontStyle: 'italic'}}>{m[2]}</Text>);
    }
    lastIndex = regex.lastIndex;
  }
  if (lastIndex < text.length) {
    spans.push(<Text key={key++}>{text.slice(lastIndex)}</Text>);
  }
  return spans;
};
