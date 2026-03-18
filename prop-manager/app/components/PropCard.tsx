import React from 'react';
import {
  View,
  Text,
  TouchableOpacity,
  StyleSheet,
  Linking,
  ActivityIndicator,
} from 'react-native';
import { PropDevice } from '../store/propStore';
import { PropStatus } from '../constants/ble';

interface Props {
  propDevice: PropDevice;
  onConnect: () => void;
  onChangeNetwork: () => void;
  onReboot: () => void;
}

const STATUS_COLORS: Record<PropStatus, string> = {
  idle: '#888',
  auth_failed: '#e53e3e',
  auth_ok: '#4299e1',
  credentials_received: '#4299e1',
  connecting: '#d69e2e',
  wifi_connected: '#38a169',
  wifi_failed: '#e53e3e',
  ap_mode: '#38a169',
  saving: '#d69e2e',
  wifi_saved: '#2b6cb0',
  disconnected: '#888',
};

const STATUS_LABELS: Record<PropStatus, string> = {
  idle: 'Idle',
  auth_failed: 'Auth Failed',
  auth_ok: 'Authenticated',
  credentials_received: 'Creds Received',
  connecting: 'Connecting…',
  wifi_connected: 'Connected',
  wifi_failed: 'Failed',
  ap_mode: 'AP Mode',
  saving: 'Saving…',
  wifi_saved: 'Saved — reboot to connect',
  disconnected: 'Disconnected',
};

export function PropCard({ propDevice, onConnect, onChangeNetwork, onReboot }: Props) {
  const { device, info, status, isConnecting } = propDevice;
  const name = info?.name ?? device.name ?? device.id;
  const port = info?.port ?? 8080;
  const state = status.state;
  const isConnected = state === 'wifi_connected' || state === 'ap_mode';
  const isFailed = state === 'wifi_failed' || state === 'auth_failed';
  const statusColor = STATUS_COLORS[state] ?? '#888';

  const openWebUI = () => {
    if (status.ip) {
      Linking.openURL(`http://${status.ip}:${port}`);
    }
  };

  return (
    <View style={styles.card}>
      <View style={styles.header}>
        <Text style={styles.name}>{name}</Text>
        <View style={[styles.badge, { backgroundColor: statusColor }]}>
          <Text style={styles.badgeText}>{STATUS_LABELS[state] ?? state}</Text>
        </View>
      </View>

      {status.ssid ? (
        <Text style={styles.detail}>Network: {status.ssid}</Text>
      ) : null}
      {status.ip ? (
        <Text style={styles.detail}>IP: {status.ip}</Text>
      ) : null}

      <View style={styles.actions}>
        {isConnecting && <ActivityIndicator size="small" color="#4299e1" style={{ marginRight: 8 }} />}

        {isConnected && (
          <>
            <TouchableOpacity style={[styles.btn, styles.btnPrimary]} onPress={openWebUI}>
              <Text style={styles.btnText}>Open WebUI</Text>
            </TouchableOpacity>
            <TouchableOpacity style={[styles.btn, styles.btnSecondary]} onPress={onChangeNetwork}>
              <Text style={styles.btnTextSecondary}>Change Network</Text>
            </TouchableOpacity>
          </>
        )}

        {(state === 'idle' || state === 'disconnected') && !isConnecting && (
          <TouchableOpacity style={[styles.btn, styles.btnPrimary]} onPress={onConnect}>
            <Text style={styles.btnText}>Connect</Text>
          </TouchableOpacity>
        )}

        {isFailed && !isConnecting && (
          <TouchableOpacity style={[styles.btn, styles.btnDanger]} onPress={onConnect}>
            <Text style={styles.btnText}>Retry</Text>
          </TouchableOpacity>
        )}

        {state === 'wifi_saved' && !isConnecting && (
          <TouchableOpacity style={[styles.btn, styles.btnReboot]} onPress={onReboot}>
            <Text style={styles.btnText}>Reboot to Connect</Text>
          </TouchableOpacity>
        )}
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  card: {
    backgroundColor: '#1a202c',
    borderRadius: 12,
    padding: 16,
    marginBottom: 12,
    borderWidth: 1,
    borderColor: '#2d3748',
  },
  header: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: 8,
  },
  name: {
    fontSize: 18,
    fontWeight: '700',
    color: '#e2e8f0',
    flex: 1,
  },
  badge: {
    borderRadius: 8,
    paddingHorizontal: 10,
    paddingVertical: 4,
  },
  badgeText: {
    color: '#fff',
    fontSize: 12,
    fontWeight: '600',
  },
  detail: {
    color: '#a0aec0',
    fontSize: 13,
    marginBottom: 4,
  },
  actions: {
    flexDirection: 'row',
    marginTop: 12,
    alignItems: 'center',
    flexWrap: 'wrap',
    gap: 8,
  },
  btn: {
    paddingHorizontal: 14,
    paddingVertical: 8,
    borderRadius: 8,
  },
  btnPrimary: { backgroundColor: '#3182ce' },
  btnSecondary: { backgroundColor: 'transparent', borderWidth: 1, borderColor: '#4a5568' },
  btnDanger: { backgroundColor: '#c53030' },
  btnReboot: { backgroundColor: '#2b6cb0' },
  btnText: { color: '#fff', fontWeight: '600', fontSize: 14 },
  btnTextSecondary: { color: '#a0aec0', fontWeight: '600', fontSize: 14 },
});
