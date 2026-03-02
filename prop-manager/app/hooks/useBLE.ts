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

// Android 12+ requires BLUETOOTH_SCAN + BLUETOOTH_CONNECT at runtime.
// All Android versions require ACCESS_FINE_LOCATION for BLE scanning.
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

  if (!allGranted) {
    console.warn('BLE permissions denied:', results);
  }
  return allGranted;
}

export function useBLE() {
  const scanningRef = useRef(false);
  const {
    upsertProp,
    setPropInfo,
    setPropStatus,
    setPropConnecting,
  } = usePropStore();

  // ── Scanning ────────────────────────────────────────────────────────────

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
          upsertProp(device.id, device);
        }
      },
    );
  }, [upsertProp]);

  const stopScan = useCallback(() => {
    manager.stopDeviceScan();
    scanningRef.current = false;
  }, []);

  // ── Connect + provision ─────────────────────────────────────────────────

  const connectAndProvision = useCallback(
    async (deviceId: string, accessCode: string, ssid: string, password: string) => {
      setPropConnecting(deviceId, true);
      try {
        const device = await manager.connectToDevice(deviceId);
        await device.discoverAllServicesAndCharacteristics();

        // 1. Read Prop Info (no auth required)
        const infoChar = await device.readCharacteristicForService(
          SERVICE_UUID,
          CHAR_PROP_INFO,
        );
        const infoStr = decode(infoChar.value);
        if (infoStr) {
          setPropInfo(deviceId, JSON.parse(infoStr) as PropInfo);
        }

        // 2. Subscribe to Status notifications before writing anything
        device.monitorCharacteristicForService(
          SERVICE_UUID,
          CHAR_STATUS,
          (err, char) => {
            if (err) {
              console.error('Status notify error:', err);
              return;
            }
            const statusStr = decode(char?.value ?? null);
            if (statusStr) {
              try {
                setPropStatus(deviceId, JSON.parse(statusStr) as StatusPayload);
              } catch {
                console.error('Failed to parse status:', statusStr);
              }
            }
          },
        );

        // 3. Read initial status
        const statusChar = await device.readCharacteristicForService(
          SERVICE_UUID,
          CHAR_STATUS,
        );
        const statusStr = decode(statusChar.value);
        if (statusStr) {
          setPropStatus(deviceId, JSON.parse(statusStr) as StatusPayload);
        }

        // 4. Authenticate
        await device.writeCharacteristicWithResponseForService(
          SERVICE_UUID,
          CHAR_AUTH,
          encode(JSON.stringify({ access_code: accessCode })),
        );

        // Wait for auth_ok status notification
        await new Promise((r) => setTimeout(r, 1200));

        const currentStatus = usePropStore.getState().props[deviceId]?.status;
        if (currentStatus?.state !== 'auth_ok') {
          console.error('Auth failed for device:', deviceId);
          return;
        }

        // 5. Write WiFi credentials
        await device.writeCharacteristicWithResponseForService(
          SERVICE_UUID,
          CHAR_WIFI_CREDS,
          encode(JSON.stringify({ ssid, password })),
        );

        // 6. Send connect_wifi command
        await device.writeCharacteristicWithResponseForService(
          SERVICE_UUID,
          CHAR_COMMAND,
          encode('connect_wifi'),
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
          SERVICE_UUID,
          CHAR_COMMAND,
          encode(command),
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

  return { startScan, stopScan, connectAndProvision, sendCommand };
}
