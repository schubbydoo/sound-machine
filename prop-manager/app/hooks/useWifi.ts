import { useCallback, useState } from 'react';
import { Platform, Alert } from 'react-native';
import WifiManager from 'react-native-wifi-reborn';

export interface WifiNetwork {
  SSID: string;
  level: number;
  capabilities: string;
}

export function useWifi() {
  const [networks, setNetworks] = useState<WifiNetwork[]>([]);
  const [scanning, setScanning] = useState(false);

  const scanNetworks = useCallback(async () => {
    setScanning(true);
    try {
      const results = await WifiManager.loadWifiList();
      const unique = Array.from(
        new Map(results.map((n) => [n.SSID, n])).values()
      ).filter((n) => n.SSID.length > 0);
      setNetworks(unique as WifiNetwork[]);
    } catch (err) {
      console.error('WiFi scan error:', err);
      Alert.alert('WiFi Scan', 'Could not scan WiFi networks. Ensure location permission is granted.');
    } finally {
      setScanning(false);
    }
  }, []);

  const joinNetwork = useCallback(async (ssid: string, password: string): Promise<boolean> => {
    try {
      await WifiManager.connectToProtectedSSID(ssid, password, false, false);
      return true;
    } catch (err) {
      console.error('WiFi join error:', err);
      return false;
    }
  }, []);

  return { networks, scanning, scanNetworks, joinNetwork };
}
