import { useEffect, useRef, useCallback } from 'react';
import { Platform, PermissionsAndroid } from 'react-native';
import { BleManager, Device, State } from 'react-native-ble-plx';
import { Buffer } from 'buffer';
import {
  SERVICE_UUID,
  CHAR_PROP_INFO,
  CHAR_AUTH,
  CHAR_WIFI_CREDS,
  CHAR_COMMAND,
  CHAR_STATUS,
  PropInfo,
  StatusPayload,
} from '../constants/ble';
import { usePropStore } from '../store/propStore';

const manager = new BleManager();

function decode(value: string | null): string {
  if (!value) return '';
  return Buffer.from(value, 'base64').toString('utf-8');
}

function encode(text: string): string {
  return Buffer.from(text, 'utf-8').toString('base64');
}

async function requestAndroidPermissions(): Promise<boolean> {
  if (Platform.OS !== 'android') return true;

  const apiLevel = typeof Platform.Version === 'number'
    ? Platform.Version
    : parseInt(Platform.Version, 10);

  const permissions: string[] = [
    PermissionsAndroid.PERMISSIONS.ACCESS_FINE_LOCATION,
  ];

  if (apiLevel >= 31) {
    permissions.push(
      PermissionsAndroid.PERMISSIONS.BLUETOOTH_SCAN,
      PermissionsAndroid.PERMISSIONS.BLUETOOTH_CONNECT,
    );
  }

  const results = await PermissionsAndroid.requestMultiple(permissions);
  const allGranted = Object.values(results).every(
    (r) => r === PermissionsAndroid.RESULTS.GRANTED,
  );
  if (!allGranted) console.warn('BLE permissions denied:', results);
  return allGranted;
}

export function useBLE() {
  const scanningRef = useRef(false);
  const {
    upsertProp,
    setPropInfo,
    setPropStatus,
    setPropConnecting,
    clearProps,
  } = usePropStore();

  // ── Auto-read Prop Info + Status on discovery (no auth required) ─────────
  // This keeps the port and status fresh without a full provision cycle.

  const readPropState = useCallback(async (device: Device) => {
    try {
      const connected = await manager.connectToDevice(device.id);
      await connected.discoverAllServicesAndCharacteristics();

      const infoChar = await connected.readCharacteristicForService(
        SERVICE_UUID, CHAR_PROP_INFO,
      );
      const infoStr = decode(infoChar.value);
      if (infoStr) setPropInfo(device.id, JSON.parse(infoStr) as PropInfo);

      const statusChar = await connected.readCharacteristicForService(
        SERVICE_UUID, CHAR_STATUS,
      );
      const statusStr = decode(statusChar.value);
      if (statusStr) setPropStatus(device.id, JSON.parse(statusStr) as StatusPayload);

      // Subscribe to ongoing status notifications
      connected.monitorCharacteristicForService(
        SERVICE_UUID,
        CHAR_STATUS,
        (err, char) => {
          if (err) return;
          const s = decode(char?.value ?? null);
          if (s) {
            try { setPropStatus(device.id, JSON.parse(s) as StatusPayload); }
            catch { /* ignore */ }
          }
        },
      );
    } catch (err) {
      console.warn('readPropState failed for', device.id, err);
    }
  }, [setPropInfo, setPropStatus]);

  // ── Scanning ─────────────────────────────────────────────────────────────

  const startScan = useCallback(async () => {
    if (scanningRef.current) return;

    const granted = await requestAndroidPermissions();
    if (!granted) {
      console.warn('BLE permissions not granted — cannot scan');
      return;
    }

    const state = await manager.state();
    if (state !== State.PoweredOn) {
      console.warn('BLE not powered on:', state);
      return;
    }

    scanningRef.current = true;
    manager.startDeviceScan(
      [SERVICE_UUID],
      { allowDuplicates: false },
      (error, device) => {
        if (error) {
          console.error('BLE scan error:', error);
          scanningRef.current = false;
          return;
        }
        if (device) {
          const isNew = !usePropStore.getState().props[device.id];
          upsertProp(device.id, device);
          if (isNew) readPropState(device);
        }
      },
    );
  }, [upsertProp, readPropState]);

  const stopScan = useCallback(() => {
    manager.stopDeviceScan();
    scanningRef.current = false;
  }, []);

  const refresh = useCallback(async () => {
    stopScan();
    clearProps();
    await startScan();
  }, [stopScan, clearProps, startScan]);

  // ── Connect + provision ───────────────────────────────────────────────────

  const connectAndProvision = useCallback(
    async (deviceId: string, accessCode: string, ssid: string, password: string) => {
      setPropConnecting(deviceId, true);
      try {
        const device = await manager.connectToDevice(deviceId);
        await device.discoverAllServicesAndCharacteristics();

        // Refresh Prop Info (gets latest port)
        const infoChar = await device.readCharacteristicForService(
          SERVICE_UUID, CHAR_PROP_INFO,
        );
        const infoStr = decode(infoChar.value);
        if (infoStr) setPropInfo(deviceId, JSON.parse(infoStr) as PropInfo);

        // Subscribe to Status notifications
        device.monitorCharacteristicForService(
          SERVICE_UUID,
          CHAR_STATUS,
          (err, char) => {
            if (err) return;
            const s = decode(char?.value ?? null);
            if (s) {
              try { setPropStatus(deviceId, JSON.parse(s) as StatusPayload); }
              catch { /* ignore */ }
            }
          },
        );

        // Read initial status
        const statusChar = await device.readCharacteristicForService(
          SERVICE_UUID, CHAR_STATUS,
        );
        const statusStr = decode(statusChar.value);
        if (statusStr) setPropStatus(deviceId, JSON.parse(statusStr) as StatusPayload);

        // Authenticate
        await device.writeCharacteristicWithResponseForService(
          SERVICE_UUID, CHAR_AUTH,
          encode(JSON.stringify({ access_code: accessCode })),
        );

        await new Promise((r) => setTimeout(r, 1200));

        const currentStatus = usePropStore.getState().props[deviceId]?.status;
        if (currentStatus?.state !== 'auth_ok') {
          console.error('Auth failed for device:', deviceId);
          return;
        }

        await device.writeCharacteristicWithResponseForService(
          SERVICE_UUID, CHAR_WIFI_CREDS,
          encode(JSON.stringify({ ssid, password })),
        );

        await device.writeCharacteristicWithResponseForService(
          SERVICE_UUID, CHAR_COMMAND,
          encode('save_wifi'),
        );
      } catch (err) {
        console.error('Provision error for', deviceId, err);
        setPropStatus(deviceId, { state: 'wifi_failed' });
      } finally {
        setPropConnecting(deviceId, false);
      }
    },
    [setPropInfo, setPropStatus, setPropConnecting],
  );

  const sendCommand = useCallback(
    async (deviceId: string, command: string) => {
      try {
        const device = await manager.connectToDevice(deviceId);
        await device.discoverAllServicesAndCharacteristics();
        await device.writeCharacteristicWithResponseForService(
          SERVICE_UUID, CHAR_COMMAND, encode(command),
        );
      } catch (err) {
        console.error('Command error:', err);
      }
    },
    [],
  );

  useEffect(() => {
    const sub = manager.onStateChange((state) => {
      if (state === State.PoweredOn) {
        startScan();
        sub.remove();
      }
    }, true);

    return () => {
      stopScan();
      sub.remove();
    };
  }, [startScan, stopScan]);

  return { startScan, stopScan, refresh, connectAndProvision, sendCommand };
}
