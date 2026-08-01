/**
 * Central Data Contract Module v2.0 — Single Source of Truth for Frontend Data Normalization
 */
export const CONTRACT_VERSION = "2.0.0";

export const CANONICAL_STATUSES = [
  'Inbound',
  'Transporting',
  'Pickup Done',
  'Created',
  'Outbound',
  'Đã hủy'
] as const;

export type CanonicalStatus = typeof CANONICAL_STATUSES[number];

export const BACKEND_STATUS_MAP: Record<string, string> = {
  'inbound':               'Inbound',
  'inbound_done':          'Inbound',
  'at_hub':                'Inbound',
  'Đang trên bãi':         'Inbound',
  'đã nhập kho':           'Inbound',
  'transporting':          'Transporting',
  'in_transit':            'Transporting',
  'chưa đến hub':          'Transporting',
  'Đang trên đường':       'Transporting',
  'đang vận chuyển':       'Transporting',
  'pickup_done':           'Pickup Done',
  'picked_up':             'Pickup Done',
  'Đã lấy hàng':           'Pickup Done',
  'created':               'Created',
  'Đã điều phối bưu cục':  'Created',
  'outbound':              'Outbound',
  'outbound_done':         'Outbound',
  'Đã xuất khỏi HUB':      'Outbound',
  'Đã rời HUB':            'Outbound',
  'đã xuất kho':           'Outbound',
  'canceled':              'Đã hủy',
  'cancelled':             'Đã hủy',
  'đã hủy':                'Đã hủy'
};

export const BACKEND_DROP_TYPE_MAP: Record<string, string> = {
  'rot_today':     'Rớt hôm nay',
  'rot_yesterday': 'Rớt hôm trước'
};

export const KEY_MAP: Record<string, string> = {
  'station_name':      'Bưu cục',
  'next_station':      'Bưu cục đích',
  'pickup_station':    'Bưu cục nộp',
  'pickup_station2':   'Bưu cục lấy thực tế',
  'status':            'Trạng thái',
  'op_date_inbound':   'Ngày vận hành_Inbound',
  'op_date_forecast':  'Ngày vận hành_Forecast',
  'op_date_pickup':    'Ngày vận hành_Pickup',
  'op_date_arrival':   'Ngày vận hành_Arrival',
  'inbound_hour':      'Inbound Hour',
  'forecast_time':     'Forecast Time',
  'pickup_time':       'Pickup Time',
  'arrival_time':      'Arrival Time',
  'drop_type':         'Loại rớt',
  'op_date':           'Ngày vận hành',
  'total_orders':      'Tổng số đơn',
  'volume':            'Volume',
  'weight_ton':        'Weight',

  'Bu cc':              'Bưu cục',
  'Trng thi':          'Trạng thái',
  'Ngy vn hnh_Inbound': 'Ngày vận hành_Inbound',
  'Ngy vn hnh_Forecast':'Ngày vận hành_Forecast',
  'Ngy vn hnh_Pickup':  'Ngày vận hành_Pickup',
  'Ngy vn hnh_Arrival': 'Ngày vận hành_Arrival',
  'Loi rt':             'Loại rớt',
  'Ngy vn hnh':         'Ngày vận hành',
  'Tng s n':           'Tổng số đơn'
};

// Micro-JSON Payload Contracts (v2.0)
export interface InboundKpiSummaryPayload {
  op_date: string;
  inbound_orders: number;
  inbound_weight_ton: number;
  forecast_total: number;
  rot_hom_truoc: number;
  rot_hom_nay: number;
  linehaul_bn_hub: number;
  contract_version?: string;
}

export interface InboundHourlyTrendPayload {
  op_date: string;
  hours: string[];
  series: {
    inbound: number[];
    transporting: number[];
    pickup_done: number[];
    created: number[];
  };
}

export interface InboundOrdersStatusPayload {
  op_date: string;
  inbound: number;
  transporting: number;
  pickup_done: number;
  created: number;
  total: number;
  inbound_weight?: number;
  transporting_weight?: number;
  pickup_done_weight?: number;
  created_weight?: number;
}

export interface TruckEtaItem {
  send_network: string;
  arrive_network: string;
  trip_code: string;
  orders_count: number;
  weight_kg: number;
  weight_ton: number;
  planned_departure?: string;
  planned_arrival?: string;
  actual_departure?: string;
  eta?: string;
  rank?: string;
  status?: string;
  op_date?: string;
}

export interface InboundTruckEtaPayload {
  op_date: string;
  trucks: TruckEtaItem[];
}

export interface OriginStationItem {
  station_name: string;
  total_volume: number;
  inbound_volume: number;
  transporting_volume: number;
  pickup_done_volume: number;
  created_volume: number;
}

export interface InboundOriginStationPayload {
  op_date: string;
  stations: OriginStationItem[];
}

export function normalizeStatus(raw: unknown): string | undefined {
  if (raw === undefined || raw === null || raw === '') return undefined;
  const key = String(raw).trim();
  return BACKEND_STATUS_MAP[key] ?? key;
}

export function normalizeDropType(raw: unknown): string | undefined {
  if (raw === undefined || raw === null || raw === '') return undefined;
  const key = String(raw).trim();
  return BACKEND_DROP_TYPE_MAP[key] ?? key;
}
