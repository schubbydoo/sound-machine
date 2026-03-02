import React, { useCallback } from 'react';
import {
  View,
  Text,
  FlatList,
  TouchableOpacity,
  StyleSheet,
  ActivityIndicator,
  SafeAreaView,
} from 'react-native';
import { Link } from 'expo-router';
import { usePropStore } from '../store/propStore';
import { useBLE } from '../hooks/useBLE';
import { PropCard } from '../components/PropCard';
import { WifiSelector } from '../components/WifiSelector';

export default function MainScreen() {
  const { props, accessCode, selectedSsid, selectedPassword } = usePropStore();
  const { connectAndProvision, sendCommand } = useBLE();

  const propList = Object.entries(props);
  const hasIdleProps = propList.some(
    ([, p]) => p.status.state === 'idle' || p.status.state === 'wifi_failed'
  );
  const hasUnconnectedProps = propList.some(
    ([, p]) =>
      p.status.state !== 'wifi_connected' && p.status.state !== 'ap_mode'
  );

  const connectAll = useCallback(async () => {
    if (!selectedSsid || !selectedPassword) return;
    for (const [id, p] of propList) {
      const state = p.status.state;
      if (state === 'idle' || state === 'wifi_failed') {
        connectAndProvision(id, accessCode, selectedSsid, selectedPassword);
      }
    }
  }, [propList, selectedSsid, selectedPassword, accessCode, connectAndProvision]);

  const handleJoinAndPush = useCallback(
    async (ssid: string, password: string) => {
      for (const [id, p] of propList) {
        const state = p.status.state;
        if (state === 'idle' || state === 'wifi_failed') {
          connectAndProvision(id, accessCode, ssid, password);
        }
      }
    },
    [propList, accessCode, connectAndProvision]
  );

  const handleConnect = useCallback(
    (deviceId: string) => {
      if (!selectedSsid || !selectedPassword) return;
      connectAndProvision(deviceId, accessCode, selectedSsid, selectedPassword);
    },
    [selectedSsid, selectedPassword, accessCode, connectAndProvision]
  );

  const handleChangeNetwork = useCallback(
    async (deviceId: string) => {
      await sendCommand(deviceId, 'disconnect_wifi');
    },
    [sendCommand]
  );

  return (
    <SafeAreaView style={styles.safe}>
      <View style={styles.container}>
        {/* Header */}
        <View style={styles.header}>
          <Text style={styles.title}>Prop Manager</Text>
          <View style={styles.headerRight}>
            <TouchableOpacity
              style={[
                styles.connectAllBtn,
                (!selectedSsid || !hasUnconnectedProps) && styles.connectAllBtnDisabled,
              ]}
              onPress={connectAll}
              disabled={!selectedSsid || !hasUnconnectedProps}
            >
              <Text style={styles.connectAllText}>Connect All</Text>
            </TouchableOpacity>
            <Link href="/settings" asChild>
              <TouchableOpacity style={styles.settingsBtn}>
                <Text style={styles.settingsIcon}>⚙</Text>
              </TouchableOpacity>
            </Link>
          </View>
        </View>

        {/* WiFi selector panel — only when idle props exist */}
        {hasIdleProps && (
          <WifiSelector onJoinAndPush={handleJoinAndPush} />
        )}

        {/* Prop list */}
        {propList.length === 0 ? (
          <View style={styles.scanning}>
            <ActivityIndicator size="large" color="#4299e1" />
            <Text style={styles.scanningText}>Scanning for props…</Text>
          </View>
        ) : (
          <FlatList
            data={propList}
            keyExtractor={([id]) => id}
            renderItem={({ item: [id, propDevice] }) => (
              <PropCard
                propDevice={propDevice}
                onConnect={() => handleConnect(id)}
                onChangeNetwork={() => handleChangeNetwork(id)}
              />
            )}
            contentContainerStyle={styles.list}
          />
        )}
      </View>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safe: {
    flex: 1,
    backgroundColor: '#0f1117',
  },
  container: {
    flex: 1,
    padding: 16,
  },
  header: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: 16,
  },
  title: {
    color: '#e2e8f0',
    fontSize: 24,
    fontWeight: '800',
  },
  headerRight: {
    flexDirection: 'row',
    gap: 8,
    alignItems: 'center',
  },
  connectAllBtn: {
    backgroundColor: '#3182ce',
    paddingHorizontal: 14,
    paddingVertical: 8,
    borderRadius: 8,
  },
  connectAllBtnDisabled: {
    backgroundColor: '#2d3748',
  },
  connectAllText: {
    color: '#fff',
    fontWeight: '700',
    fontSize: 14,
  },
  settingsBtn: {
    padding: 8,
  },
  settingsIcon: {
    fontSize: 22,
    color: '#718096',
  },
  scanning: {
    flex: 1,
    justifyContent: 'center',
    alignItems: 'center',
    gap: 16,
  },
  scanningText: {
    color: '#718096',
    fontSize: 16,
  },
  list: {
    paddingBottom: 24,
  },
});
