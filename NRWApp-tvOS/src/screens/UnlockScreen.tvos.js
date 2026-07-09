/**
 * NRW tvOS — Unlock screen (owner-only, once per device)
 *
 * The owner pastes his Plex token + server URL here a single time on his own
 * Apple TV. It's stored locally (AsyncStorage) and never leaves the device or
 * enters the repo. After saving we fetch his library so NRW buttons appear.
 * A tester who opens this screen but has no token simply can't proceed.
 */

import React, { useState, useCallback, useEffect } from 'react';
import {
  View, Text, TextInput, TouchableOpacity, StyleSheet, ActivityIndicator,
} from 'react-native';
import { useNavigation, useRoute } from '@react-navigation/native';
import { Colors } from '../constants/colors';
import { setPlexConfig, clearPlexConfig, refreshLibraryMap, getLastDiag } from '../services/plexClient.tvos';

const TEAL = '#00d4aa';

const UnlockScreen = () => {
  const navigation = useNavigation();
  const route = useRoute();
  const [token, setToken] = useState('');
  const [server, setServer] = useState('https://');
  const [busy, setBusy] = useState(false);
  const [status, setStatus] = useState('');

  const doUnlock = useCallback(async (tk, sv) => {
    if (!tk || !tk.trim() || !sv || !sv.trim() || sv.trim() === 'https://') {
      setStatus('Enter both your access token and server address.');
      return;
    }
    setBusy(true);
    setStatus('Connecting to your server…');
    try {
      await setPlexConfig(tk, sv);
      const map = await refreshLibraryMap();
      const n = map ? Object.keys(map).length : 0;
      if (n > 0) {
        setStatus('Unlocked — ' + n + ' films in your library.');
        setTimeout(() => { if (navigation.canGoBack()) navigation.goBack(); }, 1400);
      } else {
        // getLastDiag() carries the real reason (HTTP 401, non-JSON, network error…)
        setStatus('No films matched — ' + (getLastDiag() || 'unknown reason') + '. Check the token/server.');
      }
    } catch (e) {
      setStatus('Could not connect: ' + (e && e.message ? e.message : e));
    } finally {
      setBusy(false);
    }
  }, [navigation]);

  const onSave = useCallback(() => doUnlock(token, server), [doUnlock, token, server]);

  // No-type unlock path: nrw://unlock?token=…&server=… fills + unlocks on open.
  // Lets us test on the simulator and lets the owner unlock without the remote.
  useEffect(() => {
    const p = route.params || {};
    if (p.token && p.server) {
      setToken(p.token);
      setServer(p.server);
      doUnlock(p.token, p.server);
    }
  }, [route.params, doUnlock]);

  const onForget = useCallback(async () => {
    await clearPlexConfig();
    setToken('');
    setServer('https://');
    setStatus('This device has been locked again.');
  }, []);

  return (
    <View style={styles.root}>
      <Text style={styles.brand}>NRW · SCREENING ROOM</Text>
      <Text style={styles.title}>Unlock this Apple TV</Text>
      <Text style={styles.sub}>
        Connect your personal server once. Your key stays on this device only.
      </Text>

      <Text style={styles.label}>PLEX ACCESS TOKEN</Text>
      <TextInput
        style={styles.input}
        value={token}
        onChangeText={setToken}
        placeholder="paste token"
        placeholderTextColor="#666"
        autoCapitalize="none"
        autoCorrect={false}
        secureTextEntry
      />

      <Text style={styles.label}>SERVER ADDRESS</Text>
      <TextInput
        style={styles.input}
        value={server}
        onChangeText={setServer}
        placeholder="https://…plex.direct:PORT"
        placeholderTextColor="#666"
        autoCapitalize="none"
        autoCorrect={false}
      />

      <View style={styles.row}>
        <TouchableOpacity onPress={onSave} activeOpacity={0.9} style={[styles.btn, styles.btnPrimary]}>
          {busy ? <ActivityIndicator color="#000" /> : <Text style={styles.btnPrimaryText}>UNLOCK</Text>}
        </TouchableOpacity>
        <TouchableOpacity onPress={onForget} activeOpacity={0.9} style={[styles.btn, styles.btnGhost]}>
          <Text style={styles.btnGhostText}>FORGET THIS DEVICE</Text>
        </TouchableOpacity>
      </View>

      {!!status && <Text style={styles.status}>{status}</Text>}
    </View>
  );
};

const styles = StyleSheet.create({
  root: { flex: 1, backgroundColor: Colors.background, paddingHorizontal: 120, paddingTop: 90 },
  brand: { color: TEAL, letterSpacing: 4, fontSize: 15, marginBottom: 18, opacity: 0.85 },
  title: { color: '#fff', fontSize: 42, fontWeight: '200', letterSpacing: 2, marginBottom: 10 },
  sub: { color: '#aaa', fontSize: 20, marginBottom: 40, maxWidth: 900 },
  label: { color: '#888', fontSize: 14, letterSpacing: 2, marginBottom: 8, marginTop: 8 },
  input: {
    backgroundColor: '#0d0d16', color: '#fff', fontSize: 22, borderRadius: 10,
    paddingHorizontal: 18, paddingVertical: 16, marginBottom: 20,
    borderWidth: 1, borderColor: 'rgba(255,255,255,0.15)', maxWidth: 1100,
  },
  row: { flexDirection: 'row', marginTop: 14 },
  btn: { borderRadius: 10, paddingVertical: 16, paddingHorizontal: 34, marginRight: 20 },
  btnPrimary: { backgroundColor: TEAL },
  btnPrimaryText: { color: '#000', fontWeight: '800', fontSize: 20, letterSpacing: 2 },
  btnGhost: { borderWidth: 1, borderColor: 'rgba(255,255,255,0.2)' },
  btnGhostText: { color: '#bbb', fontWeight: '600', fontSize: 18, letterSpacing: 1 },
  status: { color: TEAL, fontSize: 20, marginTop: 28 },
});

export default UnlockScreen;
