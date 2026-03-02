import React, { useState, useEffect } from 'react';
import {
  View,
  Text,
  TextInput,
  TouchableOpacity,
  FlatList,
  ActivityIndicator,
  StyleSheet,
} from 'react-native';
import { useWifi, WifiNetwork } from '../hooks/useWifi';
import { usePropStore } from '../store/propStore';

interface Props {
  onJoinAndPush: (ssid: string, password: string) => Promise<void>;
}

export function WifiSelector({ onJoinAndPush }: Props) {
  const { networks, scanning, scanNetworks, joinNetwork } = useWifi();
  const { selectedSsid, selectedPassword, setWifiCredentials } = usePropStore();
  const [password, setPassword] = useState(selectedPassword);
  const [pushing, setPushing] = useState(false);

  useEffect(() => {
    scanNetworks();
  }, []);

  const handleSelect = (ssid: string) => {
    setWifiCredentials(ssid, password);
  };

  const handleJoinAndPush = async () => {
    if (!selectedSsid || !password) return;
    setPushing(true);
    setWifiCredentials(selectedSsid, password);
    await joinNetwork(selectedSsid, password);
    await onJoinAndPush(selectedSsid, password);
    setPushing(false);
  };

  const renderNetwork = ({ item }: { item: WifiNetwork }) => {
    const selected = item.SSID === selectedSsid;
    const isSecure = item.capabilities?.includes('WPA') || item.capabilities?.includes('WEP');
    const strength = item.level > -50 ? 'Strong' : item.level > -70 ? 'Good' : 'Weak';

    return (
      <TouchableOpacity
        style={[styles.networkItem, selected && styles.networkItemSelected]}
        onPress={() => handleSelect(item.SSID)}
      >
        <Text style={[styles.ssidText, selected && styles.ssidTextSelected]}>
          {item.SSID}
        </Text>
        <Text style={styles.networkMeta}>
          {strength} {isSecure ? '🔒' : '🔓'}
        </Text>
      </TouchableOpacity>
    );
  };

  return (
    <View style={styles.container}>
      <View style={styles.header}>
        <Text style={styles.title}>Select WiFi Network</Text>
        <TouchableOpacity onPress={scanNetworks} disabled={scanning}>
          {scanning ? (
            <ActivityIndicator size="small" color="#4299e1" />
          ) : (
            <Text style={styles.refreshBtn}>Refresh</Text>
          )}
        </TouchableOpacity>
      </View>

      <FlatList
        data={networks}
        keyExtractor={(n) => n.SSID}
        renderItem={renderNetwork}
        style={styles.list}
        ListEmptyComponent={
          scanning ? null : (
            <Text style={styles.emptyText}>No networks found. Tap Refresh.</Text>
          )
        }
      />

      {selectedSsid ? (
        <View style={styles.credForm}>
          <Text style={styles.selectedLabel}>Selected: {selectedSsid}</Text>
          <TextInput
            style={styles.input}
            placeholder="Password"
            placeholderTextColor="#718096"
            secureTextEntry
            value={password}
            onChangeText={(v) => {
              setPassword(v);
              setWifiCredentials(selectedSsid, v);
            }}
            autoCapitalize="none"
          />
          <TouchableOpacity
            style={[styles.joinBtn, (!selectedSsid || pushing) && styles.joinBtnDisabled]}
            onPress={handleJoinAndPush}
            disabled={!selectedSsid || pushing}
          >
            {pushing ? (
              <ActivityIndicator size="small" color="#fff" />
            ) : (
              <Text style={styles.joinBtnText}>Join & Push to All Props</Text>
            )}
          </TouchableOpacity>
        </View>
      ) : null}
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    backgroundColor: '#1a202c',
    borderRadius: 12,
    padding: 16,
    marginBottom: 16,
    borderWidth: 1,
    borderColor: '#2d3748',
    maxHeight: 380,
  },
  header: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: 12,
  },
  title: {
    color: '#e2e8f0',
    fontSize: 16,
    fontWeight: '700',
  },
  refreshBtn: {
    color: '#4299e1',
    fontSize: 14,
    fontWeight: '600',
  },
  list: {
    maxHeight: 160,
  },
  networkItem: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    padding: 10,
    borderRadius: 8,
    marginBottom: 4,
    backgroundColor: '#2d3748',
  },
  networkItemSelected: {
    backgroundColor: '#2b4c7e',
    borderWidth: 1,
    borderColor: '#4299e1',
  },
  ssidText: {
    color: '#a0aec0',
    fontSize: 14,
  },
  ssidTextSelected: {
    color: '#e2e8f0',
    fontWeight: '600',
  },
  networkMeta: {
    color: '#718096',
    fontSize: 12,
  },
  emptyText: {
    color: '#718096',
    textAlign: 'center',
    padding: 16,
  },
  credForm: {
    marginTop: 12,
  },
  selectedLabel: {
    color: '#a0aec0',
    fontSize: 13,
    marginBottom: 8,
  },
  input: {
    backgroundColor: '#2d3748',
    color: '#e2e8f0',
    borderRadius: 8,
    padding: 12,
    fontSize: 14,
    marginBottom: 10,
    borderWidth: 1,
    borderColor: '#4a5568',
  },
  joinBtn: {
    backgroundColor: '#3182ce',
    borderRadius: 8,
    padding: 14,
    alignItems: 'center',
  },
  joinBtnDisabled: {
    backgroundColor: '#2d3748',
  },
  joinBtnText: {
    color: '#fff',
    fontWeight: '700',
    fontSize: 15,
  },
});
