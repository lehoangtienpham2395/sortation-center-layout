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

export function useRealtimeSyncV2(serverUrl: string = 'ws://127.0.0.1:8088') {
  const [isConnected, setIsConnected] = useState<boolean>(false);
  const [liveData, setLiveData] = useState<LivePayload | null>(null);
  const [lastSyncTime, setLastSyncTime] = useState<string>('');

  useEffect(() => {
    let ws: WebSocket | null = null;
    let timer: any = null;

    const connect = () => {
      try {
        ws = new WebSocket(serverUrl);

        ws.onopen = () => {
          setIsConnected(true);
          console.log('🟢 [REALTIME V2] Connected to Live Server ws://127.0.0.1:8088');
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
          // Auto reconnect after 5 seconds
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
  }, [serverUrl]);

  return { isConnected, liveData, lastSyncTime };
}
