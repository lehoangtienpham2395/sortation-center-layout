import { useState, useEffect } from 'react';

export interface LivePayload {
  last_update?: string;
  rot_hom_truoc?: number;
  rot_hom_nay?: number;
  daily_snapshots?: Record<string, {
    rot_hom_truoc: number;
    rot_hom_nay: number;
    rot_ton_dong: number;
    is_frozen?: boolean;
  }>;
}

export function useRealtimeSyncV2(overrideUrl?: string) {
  const [isConnected, setIsConnected] = useState<boolean>(false);
  const [liveData, setLiveData] = useState<LivePayload | null>(null);
  const [lastSyncTime, setLastSyncTime] = useState<string>('');

  useEffect(() => {
    let ws: WebSocket | null = null;
    let timer: any = null;

    // Dynamically derive WebSocket URL from window.location.hostname for LAN / WAN support
    const hostname = typeof window !== 'undefined' && window.location.hostname ? window.location.hostname : '127.0.0.1';
    const serverUrl = overrideUrl || `ws://${hostname}:8088`;

    const connect = () => {
      try {
        ws = new WebSocket(serverUrl);

        ws.onopen = () => {
          setIsConnected(true);
          console.log(`🟢 [REALTIME V2] Connected to Live Server ${serverUrl}`);
        };

        ws.onmessage = (event) => {
          try {
            const msg = JSON.parse(event.data);
            if (msg.type === 'REALTIME_UPDATE' && msg.data) {
              setLiveData(msg.data);
              setLastSyncTime(new Date().toLocaleTimeString());
            }
          } catch (e) {
            console.warn('⚠️ WebSocket message parse error:', e);
          }
        };

        ws.onclose = () => {
          setIsConnected(false);
          timer = setTimeout(connect, 5000);
        };

        ws.onerror = () => {
          setIsConnected(false);
          if (ws) ws.close();
        };
      } catch (err) {
        setIsConnected(false);
        timer = setTimeout(connect, 5000);
      }
    };

    connect();

    return () => {
      if (ws) ws.close();
      if (timer) clearTimeout(timer);
    };
  }, [overrideUrl]);

  return { isConnected, liveData, lastSyncTime };
}
