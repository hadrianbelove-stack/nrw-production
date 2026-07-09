/**
 * NRW tvOS — Screening Room player
 *
 * A real navigation route (like TrailerScreen) that plays a personal-library
 * film via Plex's HLS transcode stream through react-native-video. This is the
 * "reskin": the owner watches inside NRW chrome, never the Plex app. MENU pops
 * the route natively (same reason TrailerScreen is a route, not an overlay).
 */

import React, { useState, useEffect, useCallback, useRef } from 'react';
import {
  View, Text, StyleSheet, ActivityIndicator, TouchableOpacity,
} from 'react-native';
import Video from 'react-native-video';
import { useNavigation, useRoute } from '@react-navigation/native';
import { Colors } from '../constants/colors';
import { buildHlsUrl } from '../services/plexClient.tvos';

const TEAL = '#00d4aa';

const PlexPlayerScreen = () => {
  const navigation = useNavigation();
  const route = useRoute();
  const { ratingKey, title, year } = route.params || {};

  const [uri, setUri] = useState(null);
  const [buffering, setBuffering] = useState(true);
  const [failed, setFailed] = useState(false);
  const mounted = useRef(true);

  useEffect(() => {
    mounted.current = true;
    (async () => {
      const u = await buildHlsUrl(ratingKey);
      if (!mounted.current) return;
      if (!u) { setFailed(true); return; }
      setUri(u);
    })();
    return () => { mounted.current = false; };
  }, [ratingKey]);

  const goBack = useCallback(() => {
    if (navigation.canGoBack()) navigation.goBack();
  }, [navigation]);

  const onError = useCallback((e) => {
    console.log('[Plex] player error:', e && JSON.stringify(e.error || e));
    setFailed(true);
  }, []);

  if (failed) {
    return (
      <View style={styles.root}>
        <Text style={styles.brand}>NRW · SCREENING ROOM</Text>
        <Text style={styles.errTitle}>Couldn’t start this film</Text>
        <Text style={styles.errSub}>
          Your server may be offline, or this device isn’t unlocked. Press MENU to go back.
        </Text>
        <TouchableOpacity onPress={goBack} activeOpacity={0.9} hasTVPreferredFocus style={styles.btn}>
          <Text style={styles.btnText}>BACK</Text>
        </TouchableOpacity>
      </View>
    );
  }

  return (
    <View style={styles.root}>
      {uri && (
        <Video
          source={{ uri }}
          style={StyleSheet.absoluteFill}
          resizeMode="contain"
          controls={true}
          paused={false}
          playInBackground={false}
          playWhenInactive={false}
          onLoadStart={() => setBuffering(true)}
          onBuffer={({ isBuffering }) => setBuffering(isBuffering)}
          onReadyForDisplay={() => setBuffering(false)}
          onError={onError}
          onEnd={goBack}
        />
      )}

      {buffering && (
        <View style={styles.spinnerWrap} pointerEvents="none">
          <ActivityIndicator size="large" color={TEAL} />
          <Text style={styles.loadingLabel}>
            {title ? title : 'Loading'}{year ? '  ·  ' + year : ''}
          </Text>
          <Text style={styles.brandFaint}>NRW · SCREENING ROOM</Text>
        </View>
      )}
    </View>
  );
};

const styles = StyleSheet.create({
  root: { flex: 1, backgroundColor: '#000', alignItems: 'center', justifyContent: 'center' },
  spinnerWrap: { position: 'absolute', alignItems: 'center' },
  loadingLabel: { color: '#fff', fontSize: 24, marginTop: 22, letterSpacing: 1 },
  brandFaint: { color: TEAL, fontSize: 13, letterSpacing: 4, marginTop: 12, opacity: 0.7 },
  brand: { color: TEAL, letterSpacing: 4, fontSize: 15, marginBottom: 20, opacity: 0.85 },
  errTitle: { color: '#fff', fontSize: 34, fontWeight: '200', marginBottom: 12 },
  errSub: { color: '#aaa', fontSize: 20, maxWidth: 800, textAlign: 'center', marginBottom: 30 },
  btn: { backgroundColor: TEAL, borderRadius: 10, paddingVertical: 14, paddingHorizontal: 40 },
  btnText: { color: '#000', fontWeight: '800', fontSize: 20, letterSpacing: 2 },
});

export default PlexPlayerScreen;
