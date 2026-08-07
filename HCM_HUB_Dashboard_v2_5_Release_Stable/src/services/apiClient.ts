/**
 * API Client Service for React Vite SPA (Enterprise Architecture v5)
 * Communicates with FastAPI backend using VITE_API_BASE and parses Standard Response Envelope.
 */

export interface ResponseMeta {
  trace_id: string;
  execution_ms: number;
  version?: string;
  current_page?: number;
  page_size?: number;
  total_records?: number;
  total_pages?: number;
}

export interface StandardEnvelope<T> {
  status: 'success' | 'error' | 'warning';
  timestamp: string;
  data: T | null;
  meta?: ResponseMeta;
}

export interface ChuteVolumeItem {
  area_id: string;
  chute_name: string;
  zone_id: number;
  total_volume: number;
  total_weight_kg: number;
  avg_weight_kg: number;
  backlog_count: number;
  last_scanned_at?: string | null;
}

export interface HourlyTrendItem {
  hour_bucket: string;
  time_label: string;
  hourly_volume: number;
  hourly_weight_kg: number;
}

export interface InboundDashboardData {
  summary_volume: number;
  summary_weight_kg: number;
  summary_avg_weight_kg: number;
  summary_backlog_volume: number;
  chutes_table: ChuteVolumeItem[];
  hourly_trend: HourlyTrendItem[];
  last_sync_timestamp?: string | null;
}

export interface OutboundStationItem {
  station_name: string;
  total_volume: number;
  total_weight_kg: number;
  avg_weight_kg: number;
  last_scanned_at?: string | null;
}

export interface OutboundDashboardData {
  summary_volume: number;
  summary_weight_kg: number;
  stations_table: OutboundStationItem[];
  last_sync_timestamp?: string | null;
}

export interface SystemHealthData {
  system_status: 'OK' | 'WARNING' | 'ERROR';
  database_connection: string;
  database_size_bytes: number;
  database_size_human: string;
  active_shipments_count: number;
  last_successful_etl_time?: string | null;
  connection_pool: {
    status: string;
    minconn: number;
    maxconn: number;
    active_used_connections: number;
    available_connections: number;
    pool_usage_percent: number;
  };
}

const API_BASE = (import.meta.env.VITE_API_BASE || 'http://localhost:8080').replace(/\/$/, '');
const API_PREFIX = '/api/v1';

export interface ApiFetchResult<T> {
  data: T | null;
  latencyMs: number;
  status: 'ok' | 'fail';
  meta?: ResponseMeta;
  errorMessage?: string;
}

async function fetchEnvelope<T>(endpoint: string, retries = 2): Promise<ApiFetchResult<T>> {
  const url = `${API_BASE}${API_PREFIX}${endpoint}`;
  let attempt = 0;
  
  while (attempt <= retries) {
    const startTime = performance.now();
    try {
      const response = await fetch(url, {
        headers: {
          'Accept': 'application/json',
          'Cache-Control': 'no-cache'
        }
      });
      const latencyMs = Math.round(performance.now() - startTime);

      if (!response.ok) {
        throw new Error(`HTTP ${response.status} when accessing ${endpoint}`);
      }

      const json: StandardEnvelope<T> = await response.json();
      if (json.status === 'error') {
        throw new Error((json as any).message || 'API returned error status');
      }

      return {
        data: json.data,
        latencyMs: json.meta?.execution_ms || latencyMs,
        status: 'ok',
        meta: json.meta
      };
    } catch (error: any) {
      attempt++;
      if (attempt > retries) {
        console.warn(`[apiClient] Failed to fetch ${url} after ${retries} retries:`, error);
        return {
          data: null,
          latencyMs: Math.round(performance.now() - startTime),
          status: 'fail',
          errorMessage: error?.message || 'Network connection failed'
        };
      }
      // Exponential backoff sleep before retry (200ms -> 400ms)
      await new Promise(r => setTimeout(r, 200 * attempt));
    }
  }

  return { data: null, latencyMs: 0, status: 'fail', errorMessage: 'Exceeded retries' };
}

export const apiClient = {
  getInboundDashboard: () => fetchEnvelope<InboundDashboardData>('/dashboard/inbound'),
  getOutboundDashboard: () => fetchEnvelope<OutboundDashboardData>('/dashboard/outbound'),
  getSystemHealth: () => fetchEnvelope<SystemHealthData>('/admin/health')
};
