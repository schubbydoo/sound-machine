import { create } from 'zustand';
import { Device } from 'react-native-ble-plx';
import { PropInfo, PropStatus, StatusPayload } from '../constants/ble';

export interface PropDevice {
  device: Device;
  info: PropInfo | null;
  status: StatusPayload;
  isConnecting: boolean;
}

interface PropStore {
  props: Record<string, PropDevice>;
  accessCode: string;
  selectedSsid: string;
  selectedPassword: string;

  // Actions
  upsertProp: (deviceId: string, device: Device) => void;
  setPropInfo: (deviceId: string, info: PropInfo) => void;
  setPropStatus: (deviceId: string, status: StatusPayload) => void;
  setPropConnecting: (deviceId: string, connecting: boolean) => void;
  removeProp: (deviceId: string) => void;
  setAccessCode: (code: string) => void;
  setWifiCredentials: (ssid: string, password: string) => void;
}

export const usePropStore = create<PropStore>((set) => ({
  props: {},
  accessCode: '',
  selectedSsid: '',
  selectedPassword: '',

  upsertProp: (deviceId, device) =>
    set((state) => ({
      props: {
        ...state.props,
        [deviceId]: state.props[deviceId] ?? {
          device,
          info: null,
          status: { state: 'idle' },
          isConnecting: false,
        },
      },
    })),

  setPropInfo: (deviceId, info) =>
    set((state) => ({
      props: {
        ...state.props,
        [deviceId]: { ...state.props[deviceId], info },
      },
    })),

  setPropStatus: (deviceId, status) =>
    set((state) => ({
      props: {
        ...state.props,
        [deviceId]: { ...state.props[deviceId], status },
      },
    })),

  setPropConnecting: (deviceId, isConnecting) =>
    set((state) => ({
      props: {
        ...state.props,
        [deviceId]: { ...state.props[deviceId], isConnecting },
      },
    })),

  removeProp: (deviceId) =>
    set((state) => {
      const next = { ...state.props };
      delete next[deviceId];
      return { props: next };
    }),

  setAccessCode: (code) => set({ accessCode: code }),

  setWifiCredentials: (ssid, password) =>
    set({ selectedSsid: ssid, selectedPassword: password }),
}));
