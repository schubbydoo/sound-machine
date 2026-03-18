// BLE UUIDs — must match daemon.py exactly
export const SERVICE_UUID    = '12345678-1234-1234-1234-123456789abc';
export const CHAR_PROP_INFO  = '12345678-1234-1234-1234-123456789ab1';
export const CHAR_AUTH       = '12345678-1234-1234-1234-123456789ab2';
export const CHAR_WIFI_CREDS = '12345678-1234-1234-1234-123456789ab3';
export const CHAR_COMMAND    = '12345678-1234-1234-1234-123456789ab4';
export const CHAR_STATUS     = '12345678-1234-1234-1234-123456789ab5';

export type PropStatus =
  | 'idle'
  | 'auth_failed'
  | 'auth_ok'
  | 'credentials_received'
  | 'connecting'
  | 'wifi_connected'
  | 'wifi_failed'
  | 'ap_mode'
  | 'saving'
  | 'wifi_saved'
  | 'disconnected';

export interface PropInfo {
  name: string;
  port: number;
}

export interface StatusPayload {
  state: PropStatus;
  ssid?: string;
  ip?: string;
}
