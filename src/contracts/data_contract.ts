/**
 * Central Data Contract Module — Single Source of Truth for Frontend Data Normalization
 */
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

export function normalizeStatus(raw: unknown): string | undefined {
  if (raw === undefined || raw === null || raw === '') return undefined;
  const key = String(raw).strip ? String(raw).strip() : String(raw).trim();
  return BACKEND_STATUS_MAP[key] ?? key;
}

export function normalizeDropType(raw: unknown): string | undefined {
  if (raw === undefined || raw === null || raw === '') return undefined;
  const key = String(raw).trim();
  return BACKEND_DROP_TYPE_MAP[key] ?? key;
}
