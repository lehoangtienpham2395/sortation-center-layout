import { useState, useEffect, useRef } from 'react';
import { motion } from 'framer-motion';
import { DatePicker } from './DatePicker';
import { getTodayOpDate } from '../utils/dateUtils';

// Animated Number Ticker Component
function NumberTicker({ value, decimals = 0 }: { value: number; decimals?: number }) {
  const ref = useRef<HTMLSpanElement>(null);
  
  useEffect(() => {
    let start = 0;
    const end = value;
    if (start === end) {
      if (ref.current) ref.current.textContent = end.toLocaleString(undefined, { minimumFractionDigits: decimals, maximumFractionDigits: decimals });
      return;
    }
    const duration = 0.8; // seconds
    let startTime: number | null = null;
    
    const animateCount = (timestamp: number) => {
      if (!startTime) startTime = timestamp;
      const progress = Math.min((timestamp - startTime) / (duration * 1000), 1);
      const current = progress * (end - start) + start;
      if (ref.current) {
        ref.current.textContent = current.toLocaleString(undefined, { minimumFractionDigits: decimals, maximumFractionDigits: decimals });
      }
      if (progress < 1) {
        window.requestAnimationFrame(animateCount);
      }
    };
    
    window.requestAnimationFrame(animateCount);
  }, [value, decimals]);

  return <span ref={ref}>0</span>;
}

interface InboundDashboardProps {
  inboundData: any[];
  linehaulData: any[];
  arrivalData: any[];
  truckEtaData: any[];
  selectedInboundDate: string;
  setSelectedInboundDate: (date: string) => void;
  loading: boolean;
  fetchAndUpdateData: () => void;
  lastUpdate?: string;
  lastUpdateObj?: any;

  kpiSummary?: any;
  hourlyTrend?: any;
  ordersStatus?: any;
  truckEtaMicro?: any;
  originStation?: any;
}

/**
 * Trích xuất giờ từ chuỗi timestamp (ví dụ: "2026-07-09 21:00" -> 21)
 * độc lập với việc check ngày/lùi ngày vì việc lọc theo ngày vận hành đã được thực hiện trước đó.
 */
function getHourFromTimestamp(val: any): number {
  if (val === undefined || val === null || val === '') return -1;
  const strVal = String(val).trim();
  if (strVal.includes(' ')) {
    const timePart = strVal.split(' ')[1] || '';
    const hour = parseInt(timePart.split(':')[0], 10);
    if (!isNaN(hour) && hour >= 0 && hour < 24) return hour;
  } else if (strVal.includes(':')) {
    const hour = parseInt(strVal.split(':')[0], 10);
    if (!isNaN(hour) && hour >= 0 && hour < 24) return hour;
  } else {
    const hour = parseInt(strVal, 10);
    if (!isNaN(hour) && hour >= 0 && hour < 24) return hour;
  }
  return -1;
}

/**
 * Trích xuất ngày vận hành từ chuỗi timestamp (ví dụ: "2026-07-16 02:00" -> "2026-07-15")
 * dựa trên giờ vận hành J&T (< 06h sáng tính cho ngày hôm trước)
 */
function getOperatingDateFromTimestamp(timestamp: string): string {
  if (!timestamp) return '';
  const match = timestamp.match(/^(\d{4}-\d{2}-\d{2})\s+(\d{2}):/);
  if (match) {
    const datePart = match[1];
    const hour = parseInt(match[2], 10);
    if (hour < 6) {
      const d = new Date(datePart);
      d.setDate(d.getDate() - 1);
      return d.toISOString().split('T')[0];
    }
    return datePart;
  }
  return '';
}

const getSvgArcPath = (cx: number, cy: number, rIn: number, rOut: number, startAngle: number, endAngle: number) => {
  const s = startAngle;
  const e = endAngle;

  const x1_out = cx + rOut * Math.cos(s);
  const y1_out = cy + rOut * Math.sin(s);
  const x2_out = cx + rOut * Math.cos(e);
  const y2_out = cy + rOut * Math.sin(e);

  const x1_in = cx + rIn * Math.cos(s);
  const y1_in = cy + rIn * Math.sin(s);
  const x2_in = cx + rIn * Math.cos(e);
  const y2_in = cy + rIn * Math.sin(e);

  const largeArcFlag = (e - s) > Math.PI ? 1 : 0;

  return `
    M ${x1_out} ${y1_out}
    A ${rOut} ${rOut} 0 ${largeArcFlag} 1 ${x2_out} ${y2_out}
    L ${x2_in} ${y2_in}
    A ${rIn} ${rIn} 0 ${largeArcFlag} 0 ${x1_in} ${y1_in}
    Z
  `.trim();
};

export default function InboundDashboard({
  inboundData,
  linehaulData,
  arrivalData,
  truckEtaData,
  truckEtaMicro,
  selectedInboundDate,
  setSelectedInboundDate,
  loading,
  fetchAndUpdateData,
  lastUpdate,
  lastUpdateObj,
  kpiSummary,
  ordersStatus,
}: InboundDashboardProps) {
  const [hoveredStatus, setHoveredStatus] = useState<string | null>(null);
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const chartInstanceRef = useRef<any | null>(null);

  // 1. Extract and sort available dates (excluding future dates > today)
  const todayOpDate = getTodayOpDate();

  const inboundDates: string[] = [];
  const startDt = new Date('2026-07-05T00:00:00');
  const endDt = new Date(`${todayOpDate}T00:00:00`);
  for (let d = new Date(endDt); d >= startDt; d.setDate(d.getDate() - 1)) {
    const yr = d.getFullYear();
    const mo = String(d.getMonth() + 1).padStart(2, '0');
    const dy = String(d.getDate()).padStart(2, '0');
    inboundDates.push(`${yr}-${mo}-${dy}`);
  }

  const activeDate = selectedInboundDate || inboundDates[0] || '';

  // 2. Filter datasets by active date
  const getWaterfallStatus = (d: any) => {
    const st = (d['status'] || d['Trạng thái'] || d['Trng thi'] || '').trim();
    if (st === 'Đã hủy' || st === 'Canceled' || st === 'Cancelled') return 'Canceled';
    const hasInbDate = Boolean(d['op_date_inbound'] || d['inbound_time'] || d['Ngày vận hành_Inbound'] || d['Ngy vn hnh_Inbound']);
    if (st === 'Inbound' || st === 'Đã nhập kho' || hasInbDate) return 'Inbound';
    if (st === 'Transporting' || st === 'Đang vận chuyển') return 'Transporting';
    if (st === 'Pickup Done' || st === 'Đã lấy hàng') return 'Pickup Done';
    return 'Created';
  };


  const getDateInbound = (d: any) => d['op_date_inbound'] || d['Ngày vận hành_Inbound'] || d['Ngy vn hnh_Inbound'];
  const getDateForecast = (d: any) => d['op_date_forecast'] || d['Ngày vận hành_Forecast'] || d['Ngy vn hnh_Forecast'];


  // Hàng Linehaul Miền Bắc (cả chiều đi và chiều về HCM HUB): pickup_station hoặc next_station là BN HUB / Hà Nội / Hải Dương / Hưng Yên
  const isLinehaulRow = (row: any) => {
    if (!row) return false;
    if (typeof row === 'string') {
      const clean = row.trim().toUpperCase();
      return clean === 'BN HUB' || clean.includes('LINEHAUL');
    }
    const pkSt = String(row?.pickup_station ?? row?.station_name ?? row?.send_network ?? row?.['Bưu cục'] ?? row?.['Pickup_station'] ?? '').trim().toUpperCase();
    const nextSt = String(row?.next_station ?? row?.['Bưu cục đến'] ?? row?.arrive_network ?? '').trim().toUpperCase();
    const rankVal = String(row?.rank ?? row?.Rank ?? '').trim().toUpperCase();
    const roundVal = String(row?.round ?? row?.Round ?? '').trim().toUpperCase();
    return pkSt === 'BN HUB' || nextSt === 'BN HUB' || rankVal === 'BN HUB' || roundVal.includes('LINEHAUL') || pkSt.startsWith('HN ') || pkSt.startsWith('HD ') || pkSt.startsWith('HY ') || nextSt.startsWith('HN ') || nextSt.startsWith('HD ') || nextSt.startsWith('HY ');
  };

  // Hàng phát sinh từ bưu cục Miền Bắc: dùng cho lọc rớt bưu cục HCM HUB
  const isNorthOriginRow = (row: any) => {
    if (!row) return false;
    if (typeof row === 'string') {
      const clean = row.trim().toUpperCase();
      return clean === 'BN HUB' || clean.startsWith('HN ') || clean.startsWith('HD ') || clean.startsWith('HY ');
    }
    const pkSt = String(row?.pickup_station ?? row?.station_name ?? row?.send_network ?? row?.['Bu cc'] ?? row?.['Bưu cục'] ?? row?.station ?? '').trim().toUpperCase();
    return pkSt === 'BN HUB' || pkSt.startsWith('HN ') || pkSt.startsWith('HD ') || pkSt.startsWith('HY ');
  };

  const isNorthRow = isNorthOriginRow;

  const normalizeDateStr = (dStr: string): string => {
    if (!dStr) return '';
    const str = String(dStr).trim();
    if (/^\d{4}-\d{2}-\d{2}/.test(str)) return str.slice(0, 10);
    const dt = new Date(str);
    if (!isNaN(dt.getTime())) {
      const yyyy = dt.getFullYear();
      const mm = String(dt.getMonth() + 1).padStart(2, '0');
      const dd = String(dt.getDate()).padStart(2, '0');
      return `${yyyy}-${mm}-${dd}`;
    }
    return str.slice(0, 10);
  };

  const isDateMatch = (dStr: string, aDate: string) => {
    if (!dStr || !aDate) return false;
    const normR = normalizeDateStr(dStr);
    const normA = normalizeDateStr(aDate);
    if (aDate.includes('..')) {
      const [start, end] = aDate.split('..');
      return normR >= normalizeDateStr(start) && normR <= normalizeDateStr(end);
    }
    return aDate.length === 7 ? normR.startsWith(normA) : normR === normA;
  };





  const getRowOpDate = (d: any) => {
    return d['Ngày vận hành'] || d['op_date'] || d['op_date_forecast'] || d['Ngày vận hành_Forecast'] || getDateForecast(d) || getDateInbound(d);
  };

  const filteredInbound = inboundData.filter(d => getWaterfallStatus(d) === 'Inbound' && isDateMatch(getRowOpDate(d), activeDate));



  /*
  const getLinehaulOperatingDate = (row: any) => {
    if (row['Ngày vận hành']) return row['Ngày vận hành'];
    const timeStr = row['unloadingStartTime'] || row['unloadingEndTime'] || row['sendTime'] || '';
    if (!timeStr) return '';
    const match = timeStr.match(/^(\d{4}-\d{2}-\d{2})\s+(\d{2}):/);
    if (match) {
      const datePart = match[1];
      const hour = parseInt(match[2], 10);
      if (hour < 6) {
        const d = new Date(datePart);
        d.setDate(d.getDate() - 1);
        return d.toISOString().split('T')[0];
      }
      return datePart;
    }
    return '';
  };
  */
  // const filteredLinehaul = linehaulData.filter(d => isDateMatch(getLinehaulOperatingDate(d), activeDate));

  // 3. Aggregate operational statistics

  let forecastShuttle = 0;
  let forecastLinehaul = 0;
  let forecastShuttleWeight = 0;
  let forecastLinehaulWeight = 0;

  // ordersWithWeight: chỉ đếm đơn có weight > 0 để tính avg chính xác
  const stagesWithWeight: Record<string, number> = {
    'Inbound': 0, 'Transporting': 0, 'Pickup Done': 0, 'Created': 0
  };

  const stages: Record<string, { orders: number; weight: number }> = {
      'Inbound': { orders: 0, weight: 0 },
      'Transporting': { orders: 0, weight: 0 },
      'Pickup Done': { orders: 0, weight: 0 },
      'Created': { orders: 0, weight: 0 }
    };

  const normActiveDate = normalizeDateStr(activeDate);
  const isHistoricalDate = normActiveDate < todayOpDate;
  let bnHubLinehaulOrdersFromInbound = 0;

  const getFcOpDate = (row: any) => {
    return normalizeDateStr(row['op_date_forecast'] || row['Ngy vn hnh_Forecast'] || row['Ngày vận hành_Forecast'] || '');
  };

  const stationTransportingMap: Record<string, number> = {};

  inboundData.forEach(d => {
    const normFcDate = getFcOpDate(d);
    const status = d.status || d['Trng thi'] || d['Trạng thái'] || '';
    const vol = parseInt(d.volume ?? d['Volume'] ?? 1, 10) || 1;
    const wt = parseFloat(d['Weight'] || d['weight_ton'] || 0) || 0;

    if (status !== 'Đã hủy' && status !== 'Canceled') {


      const arrOpDate = normalizeDateStr(d['op_date_arrival'] || d['Ngày vận hành_Arrival'] || d['Ngy vn hnh_Arrival'] || (d['Arrival Time'] ? getOperatingDateFromTimestamp(d['Arrival Time']) : ''));
      const pkOpDate  = normalizeDateStr(d['op_date_pickup']  || d['Ngày vận hành_Pickup']  || d['Ngy vn hnh_Pickup']  || '');
      const inbOpDate = normalizeDateStr(d['op_date_inbound'] || d['Ngày vận hành_Inbound'] || d['Ngy vn hnh_Inbound'] || '');

      const isOpMatch = (normFcDate === normActiveDate) || (arrOpDate === normActiveDate) || (pkOpDate === normActiveDate) || (inbOpDate === normActiveDate);

      // 🎯 BIỂU ĐỒ ORDERS STATUS TÍNH TẤT CẢ CÁC ĐƠN THUỘC CA VẬN HÀNH HÔM NAY
      if (isOpMatch) {
        const wfStatus = getWaterfallStatus(d);
        if (stages[wfStatus]) {
          stages[wfStatus].orders += vol;
          stages[wfStatus].weight += wt;
          if (wt > 0) stagesWithWeight[wfStatus] += vol;
        }

        // 🎯 TÍNH THẺ FORECAST = TỔNG SẢN LƯỢNG CẦN XỬ LÝ TRONG NGÀY (BAO GỒM CẢ ĐƠN ĐÃ INBOUND)
        if (isLinehaulRow(d)) {
          forecastLinehaul += vol;
          forecastLinehaulWeight += wt;
        } else {
          forecastShuttle += vol;
          forecastShuttleWeight += wt;
        }

        if (wfStatus === 'Transporting') {
          const pkSt = (d['pickup_station'] || d['station_name'] || '').trim().toUpperCase();
          if (pkSt && pkSt !== 'BN HUB') {
            stationTransportingMap[pkSt] = (stationTransportingMap[pkSt] || 0) + vol;
          }
        }
      }
    }
  });

  console.log('[DEBUG BROWSER STAGES]', activeDate, JSON.stringify(stages));

  // Priority: truckEtaMicro (inbound_truck_eta.json) > truckEtaData (truck_eta.json)
  const rawTrucksList: any[] = (() => {
    if (truckEtaMicro?.trucks && truckEtaMicro.trucks.length > 0) return truckEtaMicro.trucks;
    if (Array.isArray(truckEtaData) && truckEtaData.length > 0) return truckEtaData;
    return (truckEtaData as any)?.trucks || [];
  })();
  console.log('[DEBUG TRUCK ETA] source:', truckEtaMicro?.trucks?.length ? 'microTruckEta' : 'truckEtaData', '| count:', rawTrucksList.length, '| microTruckEta trucks:', truckEtaMicro?.trucks?.length ?? 0);





  const filteredTruckEta = rawTrucksList
    .filter((d: any) => {
      const opD = d.op_date || getOperatingDateFromTimestamp(d.eta || d.planned_arrival || '');
      return !opD || isDateMatch(opD, activeDate);
    })
    .map((d: any) => ({
      ...d,
      'Mã chuyến': d.shipmentName || d.plateNumber || d.plate_number || d.trip_code || 'DIRECT',
      'Biển số': d.plateNumber || d.plate_number || d.trip_code || 'DIRECT',
      'Nhà xe': d.carrierName || d.carrier_name || 'J&T Express',
      'Bưu cục đi': d.send_network || d.sendNetworkName || d['Bưu cục đi'] || 'BN HUB',
      'Bưu cục đến': d.arrive_network || d.arriveNetworkName || d['Bưu cục đến'] || 'HCM HUB',
      'Tổng số đơn': d.orders_count ?? d.loadscanwaybillnum ?? d.volume ?? 0,
      'Tổng trọng lượng (kg)': d.weight_kg ?? d.loadpackageweight ?? 0,
      'Giờ đến bãi': d.transporting_time || d.transport_time || d.transportingTime || d.actual_departure || d.planned_departure || ''
    }));

  // Group truck ETA by unique station (Bảo vệ ngày lịch sử: không rò xe live ngày 30/07 sang ngày lịch sử)
  const effectiveTruckEta = (filteredTruckEta && filteredTruckEta.length > 0) ? filteredTruckEta : (isHistoricalDate ? [] : rawTrucksList);
  const groupedStationVehicles: Record<string, any> = {};

  (effectiveTruckEta || []).forEach((d: any, idx: number) => {
    const st = (d['send_network'] || d['sendNetworkName'] || d['Station'] || d['Pickup_station'] || d['Bưu cục đi'] || d['send_site_name'] || '').trim();
    if (!st) return;
    const cleanKey = st.toUpperCase();

    const tongDon = Number(d['Tổng số đơn'] ?? d['orders_count'] ?? d['loadscanwaybillnum'] ?? d['volume'] ?? 0);
    const lastTime = d['transporting_time'] || d['transport_time'] || d['transportingTime'] || d['actual_departure'] || d['planned_departure'] || '';
    const wtKg = Number(d['weight_kg'] ?? d['loadpackageweight'] ?? d['Tổng trọng lượng (kg)'] ?? 0);
    const wtTon = Number(d['weight'] ?? d['weight_ton'] ?? d['package_charge_weight'] ?? 0);
    const wt = wtKg > 0 ? wtKg / 1000.0 : (wtTon > 100 ? wtTon / 1000.0 : wtTon);

    if (!groupedStationVehicles[st]) {
      groupedStationVehicles[st] = {
        station: st,
        trucking: 0,
        orders: tongDon,
        weight: 0,
        eta: lastTime,
        rank: (cleanKey.includes('BN') || cleanKey.includes('NORTH')) ? 'Linehaul' : (d['rank'] || d['Rank'] || 'Shuttle'),
        chuaDenHub: tongDon,
        tongDon: tongDon,
        vehicles: 0,
        vehicleSet: new Set(),
        lastTime: lastTime
      };
    } else {
      groupedStationVehicles[st].orders += tongDon;
      groupedStationVehicles[st].tongDon += tongDon;
      groupedStationVehicles[st].chuaDenHub += tongDon;
    }

    const tripId = d.trip_code || d.shipmentName || d.plateNumber || d.plate_number || `${st}_${idx}`;
    groupedStationVehicles[st].vehicleSet.add(String(tripId));
    groupedStationVehicles[st].vehicles = groupedStationVehicles[st].vehicleSet.size;
    groupedStationVehicles[st].trucking = groupedStationVehicles[st].vehicles;
    groupedStationVehicles[st].weight += wt;
    if (lastTime && lastTime > groupedStationVehicles[st].lastTime) {
      groupedStationVehicles[st].lastTime = lastTime;
      groupedStationVehicles[st].eta = lastTime;
    }
  });


  // Dự phòng an toàn: Nếu truckEtaData chưa tải xong, tự động tạo danh sách xe di chuyển từ arrivalData
  if (Object.keys(groupedStationVehicles).length === 0 && arrivalData && arrivalData.length > 0) {
    (arrivalData || []).forEach((d: any) => {
      const st = (d['station_name'] || d['Pickup_station'] || d['Bưu cục'] || d['send_network'] || '').trim();
      if (!st) return;
      const cleanKey = st.toUpperCase();

      const inTransitOrders = Number(d['not_hub'] ?? d['Chưa đến Hub'] ?? d['Chua dn Hub'] ?? d['Orders'] ?? d['total_orders'] ?? 0);
      const tongDon = Number(d['total_orders'] ?? d['Tổng số đơn'] ?? d['Orders'] ?? 0);
      const lastTime = d['last_scan_time'] || d['scan_hour'] || d['ETA'] || '';

      if (inTransitOrders > 0 || tongDon > 0) {
        if (!groupedStationVehicles[st]) {
          groupedStationVehicles[st] = {
            station: st,
            trucking: 1,
            orders: inTransitOrders > 0 ? inTransitOrders : tongDon,
            weight: 0,
            eta: lastTime,
            rank: (cleanKey.includes('BN') || cleanKey.includes('NORTH')) ? 'Linehaul' : 'Shuttle',
            chuaDenHub: inTransitOrders,
            tongDon: tongDon,
            vehicles: 1,
            vehicleSet: new Set([st]),
            lastTime: lastTime
          };
        } else {
          groupedStationVehicles[st].orders += (inTransitOrders > 0 ? inTransitOrders : tongDon);
          groupedStationVehicles[st].tongDon += tongDon;
          groupedStationVehicles[st].chuaDenHub += inTransitOrders;
        }
      }
    });
  }

  let incomingVehicles = Object.values(groupedStationVehicles)
    .filter(v => v.orders > 0 || v.tongDon > 0)
    .sort((a, b) => b.orders - a.orders);


  // Split by Shuttle and Linehaul ranks
  const shuttleVehicles = incomingVehicles.filter(v => v.rank === 'Shuttle');
  const linehaulVehicles = incomingVehicles.filter(v => v.rank === 'Linehaul');

  let totalShuttleVehicles = shuttleVehicles.reduce((sum, v) => sum + (v.vehicles || 1), 0);
  let totalLinehaulVehicles = linehaulVehicles.reduce((sum, v) => sum + (v.vehicles || 1), 0);
  let totalTransitVehicles = totalShuttleVehicles + totalLinehaulVehicles;
  let totalInTransitOrders = incomingVehicles.reduce((sum, s) => sum + s.orders, 0);
  let totalInTransitWeight = incomingVehicles.reduce((sum, s) => sum + s.weight, 0);

  let bnHubLinehaulOrders = bnHubLinehaulOrdersFromInbound;
  const bnHubObj = incomingVehicles.find(v => (v.name || v.station || '').toUpperCase().includes('BN HUB'));
  if (bnHubObj && bnHubObj.orders > 0) {
    bnHubLinehaulOrders = Math.max(bnHubLinehaulOrders, bnHubObj.orders || bnHubObj.tongDon || 0);
  }


  const isFutureDate = normActiveDate > todayOpDate;

  const [localKpiSummary, setLocalKpiSummary] = useState<any | null>(null);
  const [localOrdersStatus, setLocalOrdersStatus] = useState<any | null>(null);

  useEffect(() => {
    if (!normActiveDate) return;
    let isMounted = true;
    const t = Date.now();
    const isHistory = normActiveDate < todayOpDate;
    const subPath = isHistory ? `history/${normActiveDate}` : 'live';
    const fetchOpts: RequestInit = { cache: 'no-store', headers: { 'Cache-Control': 'no-cache, no-store, must-revalidate', 'Pragma': 'no-cache' } };

    fetch(`./data/${subPath}/inbound_kpi_summary.json?t=${t}`, fetchOpts)
      .then(res => res.ok ? res.json() : null)
      .then(data => {
        if (isMounted && data) {
          setLocalKpiSummary(data);
        }
      })
      .catch(() => {
        if (isMounted) setLocalKpiSummary(null);
      });

    fetch(`./data/${subPath}/inbound_orders_status.json?t=${t}`, fetchOpts)
      .then(res => res.ok ? res.json() : null)
      .then(data => {
        if (isMounted && data) {
          setLocalOrdersStatus(data);
        }
      })
      .catch(() => {
        if (isMounted) setLocalOrdersStatus(null);
      });

    return () => { isMounted = false; };
  }, [normActiveDate, todayOpDate]);

  // 🎯 Rebuild 4 Module (Forecast, Orders Status, Update, Truck ETA) theo Micro-JSON v2.0
  const effectiveKpiSummary = (localKpiSummary && localKpiSummary.op_date === normActiveDate)
    ? localKpiSummary
    : ((kpiSummary && kpiSummary.op_date === normActiveDate) ? kpiSummary : null);

  const effectiveOrdersStatus = (localOrdersStatus && localOrdersStatus.op_date === normActiveDate)
    ? localOrdersStatus
    : ((ordersStatus && ordersStatus.op_date === normActiveDate) ? ordersStatus : null);

  const snapshotForDate = (lastUpdateObj?.daily_snapshots as Record<string, any>)?.[normActiveDate];

  const totalInbound     = isFutureDate ? 0 : (effectiveOrdersStatus?.inbound     || effectiveKpiSummary?.inbound_orders || snapshotForDate?.inbound_orders || snapshotForDate?.inbound || stages['Inbound'].orders);
  const totalInTransit   = isFutureDate ? 0 : (effectiveOrdersStatus?.transporting  || stages['Transporting'].orders);
  const totalPickupDone  = isFutureDate ? 0 : (effectiveOrdersStatus?.pickup_done   || stages['Pickup Done'].orders);
  const totalCreated     = isFutureDate ? 0 : (effectiveOrdersStatus?.created       || stages['Created'].orders);

  // 🎯 FORECAST = TỔNG SẢN LƯỢNG CẦN XỬ LÝ TRONG NGÀY (CỐ ĐỊNH BAN ĐẦU - SOURCE OF TRUTH)
  // FORECAST LÀ SỐ LIỆU CỐ ĐỊNH KHÔNG THỂ TỰ ĐỘNG GIẢM KHI QUÉT INBOUND
  const finalShuttleForecast = isFutureDate ? 0 : (
    effectiveKpiSummary?.shuttle ??
    snapshotForDate?.shuttle ??
    forecastShuttle
  );

  // 🎯 QUY TẮC KHÔNG TÍNH LINEHAUL DỰ BÁO TỪ BN HUB VỀ (SET BẰNG 0)
  const finalLinehaulForecast = 0;
  const finalLinehaulWeight = 0;

  const totalForecast = finalShuttleForecast;
  const finalShuttleWeight = isFutureDate ? 0 : (effectiveKpiSummary?.shuttle_weight ?? forecastShuttleWeight);
  const totalForecastWeight = finalShuttleWeight;

  console.log('[DEBUG FORECAST KPI]', { normActiveDate, kpiOpDate: kpiSummary?.op_date, kpiFc: kpiSummary?.forecast_total, snapFc: snapshotForDate?.forecast_total, totalForecast, finalShuttleForecast, finalLinehaulForecast });

  if (isFutureDate || isHistoricalDate) {
    incomingVehicles = [];
    totalShuttleVehicles = 0;
    totalLinehaulVehicles = 0;
    totalTransitVehicles = 0;
    totalInTransitOrders = 0;
    totalInTransitWeight = 0;
    bnHubLinehaulOrders = 0;
  }

  if (totalInTransitOrders > 0 && stages['Transporting'].weight === 0) {
    stages['Transporting'].weight = totalInTransitWeight;
  }

  // 4. Hourly timelines
  const hours24 = [];
  for (let i = 6; i < 24; i++) hours24.push(i);
  for (let i = 0; i < 6; i++) hours24.push(i);
  const labels = hours24.map(h => `${String(h).padStart(2, '0')}:00`);

  const hourlyInbound: Record<string, number> = {};
  const hourlyArrived: Record<string, number> = {};
  const hourlyForecast: Record<string, number> = {};
  const hourlyPickup: Record<string, number> = {};
  
  labels.forEach(l => {
    hourlyInbound[l] = 0;
    hourlyArrived[l] = 0;
    hourlyForecast[l] = 0;
    hourlyPickup[l] = 0;
  });

  // 1. Transporting hourly: tính từ mốc thời gian phát hàng (Arrival Time / scantime) trong inboundData
  //    - Lấy theo cycle 6-6 (mốc thời gian < 06:00 sáng thuộc ngày vận hành hôm trước)
  //    - Gắn trực tiếp lên bộ lọc ngày activeDate
  inboundData.forEach(d => {
    if (isNorthRow(d)) return;

    const arrTime = d['Arrival Time'] || d['Arrival_time'] || d['arrival_time'] || '';
    if (!arrTime) return;

    // Tính ngày vận hành (cycle 6-6) từ Arrival Time
    const arrOpDate = d['Ngy vn hnh_Arrival'] || d['Ngày vận hành_Arrival'] || getOperatingDateFromTimestamp(arrTime);

    // Gắn lên bộ lọc ngày activeDate
    if (arrOpDate !== activeDate) return;

    // Lấy giờ thực tế (00-23h) từ Arrival Time
    const hrVal = getHourFromTimestamp(arrTime);
    if (hrVal >= 0 && hrVal < 24) {
      const hour = `${String(hrVal).padStart(2, '0')}:00`;
      const vol = parseInt(d['Volume'] || 1, 10);
      if (hourlyArrived[hour] !== undefined) {
        hourlyArrived[hour] += vol;
      }
    }
  });

  // 2. Forecast Time (Dự báo - Kế hoạch lấy): Hiển thị tất cả đơn có Ngày vận hành_Forecast hoặc ngày vận hành của Forecast Time khớp với activeDate
  inboundData.filter(d => {
    const fcTime = d['Forecast Time'] || d['forecast_time'] || '';
    const fcDate = getOperatingDateFromTimestamp(fcTime);
    const opDate = d['Ngy vn hnh_Forecast'] || d['Ngày vận hành_Forecast'] || '';
    return opDate === activeDate || fcDate === activeDate;
  }).forEach(d => {
    if (isNorthRow(d)) {
      return;
    }
    const fcTime = d['Forecast Time'] || d['forecast_time'] || '';
    if (fcTime) {
      const fcDate = getOperatingDateFromTimestamp(fcTime);
      const loaiRot = d['Loi rt'] || d['Loại rớt'] || '';
      // Nếu là ngày forecast gốc (fcDate === activeDate), ta HIỂN THỊ bất kể loaiRot là gì để giữ đúng lịch sử ca đêm
      // Nếu là ngày gối đầu (opDate === activeDate và fcDate !== activeDate), ta lọc bỏ 'Rớt hôm trước' để tránh lặp lại
      if (fcDate === activeDate || loaiRot !== 'Rớt hôm trước') {
        const hrVal = getHourFromTimestamp(fcTime);
        if (hrVal >= 0 && hrVal < 24) {
          const hour = `${String(hrVal).padStart(2, '0')}:00`;
          if (hourlyForecast[hour] !== undefined) {
            hourlyForecast[hour] += parseInt(d['Volume'], 10) || 0;
          }
        }
      }
    }
  });

  // 3. Pickup Time (Shipper đã lấy): CHỈ đếm các đơn có mốc lấy hàng thực tế và trạng thái đã lấy hàng (Pickup Done / Transporting / Inbound)
  // 3. Pickup Time (Shipper đã lấy): CHỈ đếm các đơn có mốc lấy hàng thuộc ngày vận hành activeDate
  inboundData.forEach(d => {
    if (isNorthRow(d)) return;
    const status = d['Trng thi'] || d['Trạng thái'] || '';
    if (status === 'Created' || status === 'Đã điều phối bưu cục') return;

    const pkTime = d['Pickup Time'] || d['pickup_time'] || '';
    const pkOpDate = d['Ngy vn hnh_Pickup'] || d['Ngày vận hành_Pickup'] || (pkTime ? getOperatingDateFromTimestamp(pkTime) : '');
    
    if (pkTime && (pkOpDate === activeDate || isDateMatch(pkOpDate, activeDate))) {
      const hrVal = getHourFromTimestamp(pkTime);
      if (hrVal >= 0 && hrVal < 24) {
        const hour = `${String(hrVal).padStart(2, '0')}:00`;
        if (hourlyPickup[hour] !== undefined) {
          hourlyPickup[hour] += parseInt(d['Volume'] || 1, 10);
        }
      }
    }
  });

  // 4. Inbound (Nhập kho HUB): Hiển thị các đơn nhập kho trong ngày activeDate
  filteredInbound.forEach(d => {
    if ((d['Trng thi'] || d['Trạng thái']) === 'Inbound') {
      const ibTime = d['Inbound Hour'] || d['inbound_hour'] || d['Inbound Time'];
      if (ibTime !== undefined && ibTime !== null && ibTime !== '') {
        const hrVal = getHourFromTimestamp(ibTime);
        if (hrVal >= 0 && hrVal < 24) {
          const hour = `${String(hrVal).padStart(2, '0')}:00`;
          if (hourlyInbound[hour] !== undefined) {
            hourlyInbound[hour] += parseInt(d['Volume'], 10) || 0;
          }
        }
      }
    }
  });

  const totalBase = totalInbound + totalInTransit + totalPickupDone + totalCreated;



  let inboundPct = totalBase > 0 ? Math.round((totalInbound / totalBase) * 100) : 0;
  let inTransitPct = totalBase > 0 ? Math.round((totalInTransit / totalBase) * 100) : 0;
  let pickupDonePct = totalBase > 0 ? Math.round((totalPickupDone / totalBase) * 100) : 0;
  let createdPct = totalBase > 0 ? Math.max(0, 100 - (inboundPct + inTransitPct + pickupDonePct)) : 0;

  const inboundTrendData  = labels.map(l => hourlyInbound[l]);
  const arrivedTrendData  = labels.map(l => hourlyArrived[l]);
  const forecastTrendData = labels.map(l => hourlyForecast[l]);
  const pickupTrendData   = labels.map(l => hourlyPickup[l]);

  const totalOrders = totalInbound;
  const totalWeight = isFutureDate ? 0 : (effectiveKpiSummary?.inbound_weight_ton ?? stages['Inbound'].weight);

  const segments = [
    { name: 'Inbound', value: totalInbound, pct: inboundPct, color: '#B8F7E4', label: 'Inbound' },
    { name: 'Transporting', value: totalInTransit, pct: inTransitPct, color: '#C8FF3D', label: 'Transporting' },
    { name: 'Pickup Done', value: totalPickupDone, pct: pickupDonePct, color: '#38BDF8', label: 'Pickup Done' },
    { name: 'Created', value: totalCreated, pct: createdPct, color: '#FC6C26', label: 'Created' }
  ];



  const activeSegments = segments.filter(s => s.pct > 0);
  const sortedSegments = [...activeSegments].sort((a, b) => b.pct - a.pct);

  const segmentLayers = new Map<string, number>();
  sortedSegments.forEach((s, index) => {
    if (index === 0) segmentLayers.set(s.name, 3);
    else if (index === 1) segmentLayers.set(s.name, 2);
    else segmentLayers.set(s.name, 1);
  });

  const gapAngle = 0.00; // 0 degrees (no gaps between segments)
  const numGaps = activeSegments.length;
  const totalGapAngle = numGaps * gapAngle;
  const availableAngle = 2 * Math.PI - totalGapAngle;

  let currentAngle = 0;
  const renderedSegments = activeSegments.map(s => {
    let angleSpan = (s.pct / 100) * availableAngle;
    if (angleSpan >= 2 * Math.PI) {
      angleSpan = 2 * Math.PI - 0.01;
    }
    const startAngle = currentAngle;
    const endAngle = currentAngle + angleSpan;
    currentAngle = endAngle + gapAngle;
    
    const layers = segmentLayers.get(s.name) || 1;
    return {
      ...s,
      startAngle,
      endAngle,
      layers
    };
  });

  const highestStatus = sortedSegments[0] || segments[0] || { name: 'Inbound', value: 0, pct: 0, color: '#B8F7E4', label: 'Inbound' };
  const activeDisplayStatus = hoveredStatus 
    ? (segments.find(s => s.name === hoveredStatus) || highestStatus)
    : highestStatus;

  // MỞ RỘNG METRICS BƯU CỤC GỬI (Option A: Chỉ đếm các chuyến xe chính >= 5 đơn)
  const fcMetrics: Record<string, { fc: string; tripCounts: Map<string, number>; orders: number; weight: number }> = {};
  const getFC = (name: any) => {
    if (!name) return null;
    const clean = String(name).trim().toUpperCase();
    if (!clean) return null;
    if (!fcMetrics[clean]) {
      fcMetrics[clean] = { fc: String(name).trim(), tripCounts: new Map(), orders: 0, weight: 0 };
    }
    return fcMetrics[clean];
  };

  filteredInbound.forEach(d => {
    const status = d.status || d['Trng thi'] || d['Trạng thái'] || '';
    if (status === 'Inbound' || status === 'Đã nhập kho') {
      const pSt = String(d.pickup_station || d.send_network || d['Bưu cục nộp'] || d['Bưu cục gốc'] || d['Bưu cục'] || d['Bu cc'] || d.station_name || '').trim();
      let rawFcName = pSt || 'Chưa rõ';
      if (pSt.toUpperCase().includes('BN HUB') || isNorthRow(pSt)) {
        rawFcName = 'BN HUB';
      }
      const fc = getFC(rawFcName);
      if (fc) {
        const vol = parseInt(d.volume ?? d['Volume'] ?? 1, 10) || 1;
        const wt = parseFloat(d.weight_ton ?? d['Weight'] ?? 0) || 0;
        fc.orders += vol;
        fc.weight += wt;
        const tripId = d.trip_code || d.trip_id || d.plate_number || d.vehicle_number || d['Phiếu nhiệm vụ'] || d['Mã chuyến xe'];
        if (tripId) {
          const tid = String(tripId).trim();
          fc.tripCounts.set(tid, (fc.tripCounts.get(tid) || 0) + vol);
        }
      }
    }
  });

  // 🎯 TÍNH SỐ XE THỰC TẾ CHUẨN VẬN HÀNH (LOẠI BỎ RÁC BẢNG KÊ NỘI BỘ, QUY ĐỔI CHUẨN TẢI TRỌNG XE VẬN CHUYỂN)
  const allSendingFCs = Object.values(fcMetrics)
    .map(item => {
      const isBn = item.fc.toUpperCase().includes('BN HUB') || item.fc.toUpperCase().includes('NORTH');
      
      // Sức chứa quy đổi chuẩn 1 xe xe tải chạy tuyến:
      // - Linehaul BN HUB: ~1,400 đơn/chuyến (ví dụ: 2,115 đơn = đúng 2 xe chuẩn)
      // - Shuttle Bưu cục (DT Sa Đéc, SG Củ Chi...): ~450 - 500 đơn/chuyến (ví dụ: DT Sa Đéc 1,096 đơn = đúng 2 xe chuẩn)
      const targetAvgOrdersPerTruck = isBn ? 1400 : 480;
      const realTrucksCount = Math.max(1, Math.round(item.orders / targetAvgOrdersPerTruck));

      return {
        fc: item.fc,
        vehicles: item.orders > 0 ? realTrucksCount : 0,
        orders: item.orders,
        weight: item.weight
      };
    })
    .filter(item => item.orders > 0 || item.vehicles > 0)
    .sort((a, b) => b.orders - a.orders || b.weight - a.weight);

  // Tính tổng số lượng để tính tỉ lệ % của từng bưu cục
  const totalSendingVehicles = allSendingFCs.reduce((sum, item) => sum + item.vehicles, 0);
  const totalSendingOrders = allSendingFCs.reduce((sum, item) => sum + item.orders, 0);
  const totalSendingWeight = allSendingFCs.reduce((sum, item) => sum + item.weight, 0);


  useEffect(() => {
    const ChartClass = (window as any).Chart;
    if (!ChartClass) return;

    if (canvasRef.current) {
      const ctx = canvasRef.current.getContext('2d');
      if (ctx) {
        if (chartInstanceRef.current) chartInstanceRef.current.destroy();

        const forecastGrad = ctx.createLinearGradient(0, 0, 0, 220);
        forecastGrad.addColorStop(0, 'rgba(252, 108, 38, 0.25)');
        forecastGrad.addColorStop(1, 'rgba(252, 108, 38, 0)');

        const pickupGrad = ctx.createLinearGradient(0, 0, 0, 220);
        pickupGrad.addColorStop(0, 'rgba(56, 189, 248, 0.25)');
        pickupGrad.addColorStop(1, 'rgba(56, 189, 248, 0)');

        const arrivedGrad = ctx.createLinearGradient(0, 0, 0, 220);
        arrivedGrad.addColorStop(0, 'rgba(200, 255, 61, 0.25)');
        arrivedGrad.addColorStop(1, 'rgba(200, 255, 61, 0)');

        const inboundGrad = ctx.createLinearGradient(0, 0, 0, 220);
        inboundGrad.addColorStop(0, 'rgba(184, 247, 228, 0.25)');
        inboundGrad.addColorStop(1, 'rgba(184, 247, 228, 0)');

        chartInstanceRef.current = new ChartClass(ctx, {
          type: 'line',
          data: {
            labels,
            datasets: [
              {
                label: 'Created',
                data: forecastTrendData,
                borderColor: '#FC6C26',
                backgroundColor: forecastGrad,
                borderWidth: 3,
                tension: 0.4,
                fill: true,
                pointBackgroundColor: '#05030a',
                pointBorderColor: '#FC6C26',
                pointBorderWidth: 2,
                pointHoverRadius: 8,
                pointRadius: 4,
                pointHoverBackgroundColor: '#FC6C26',
                pointHoverBorderWidth: 3
              },
              {
                label: 'Pickup Done',
                data: pickupTrendData,
                borderColor: '#38BDF8',
                backgroundColor: pickupGrad,
                borderWidth: 3,
                tension: 0.4,
                fill: true,
                pointBackgroundColor: '#05030a',
                pointBorderColor: '#38BDF8',
                pointBorderWidth: 2,
                pointHoverRadius: 8,
                pointRadius: 4,
                pointHoverBackgroundColor: '#38BDF8',
                pointHoverBorderWidth: 3
              },
              {
                label: 'Transporting',
                data: arrivedTrendData,
                borderColor: '#C8FF3D',
                backgroundColor: arrivedGrad,
                borderWidth: 3,
                tension: 0.4,
                fill: true,
                pointBackgroundColor: '#05030a',
                pointBorderColor: '#C8FF3D',
                pointBorderWidth: 2,
                pointHoverRadius: 8,
                pointRadius: 4,
                pointHoverBackgroundColor: '#C8FF3D',
                pointHoverBorderWidth: 3
              },
              {
                label: 'Inbound',
                data: inboundTrendData,
                borderColor: '#B8F7E4',
                backgroundColor: inboundGrad,
                borderWidth: 3,
                tension: 0.4,
                fill: true,
                pointBackgroundColor: '#05030a',
                pointBorderColor: '#B8F7E4',
                pointBorderWidth: 2,
                pointHoverRadius: 8,
                pointRadius: 4,
                pointHoverBackgroundColor: '#B8F7E4',
                pointHoverBorderWidth: 3
              }
            ]
          },
          options: {
            responsive: true,
            maintainAspectRatio: false,
            interaction: {
              mode: 'index',
              intersect: false
            },
            plugins: {
              legend: { display: false },
              tooltip: {
                mode: 'index',
                intersect: false,
                backgroundColor: '#120f22',
                titleColor: '#fff',
                bodyColor: '#a0aec0',
                borderColor: 'rgba(139, 92, 246, 0.2)',
                borderWidth: 1,
                padding: 10,
                displayColors: true,
                callbacks: {
                  label: function (context: any) {
                    return ` ${context.dataset.label}: ${context.raw.toLocaleString()} đơn`;
                  }
                }
              }
            },
            scales: {
              x: {
                grid: { display: false },
                ticks: { color: '#a0aec0', font: { size: 9 } }
              },
              y: {
                grid: { display: false },
                ticks: { color: '#a0aec0', font: { size: 9 } }
              }
            }
          }
        });
      }
    }
  }, [activeDate, loading, inboundData.length, linehaulData.length, truckEtaData.length]);

  const handleExportCSV = () => {
    if (!filteredInbound || filteredInbound.length === 0) {
      alert('Không có dữ liệu Inbound để xuất!');
      return;
    }
    const headers = ['Bưu cục', 'Trạng thái', 'Volume', 'Weight', 'Ngày vận hành_Inbound', 'Loại rớt'];
    const rows = filteredInbound.map(d => [
      `"${d['Bưu cục'] || d['Bưu cục'] || ''}"`,
      `"${d['Trạng thái'] || d['Trạng thái'] || ''}"`,
      d['Volume'] || 0,
      d['Weight'] || 0,
      `"${d['Ngày vận hành_Inbound'] || ''}"`,
      `"${d['Loại rớt'] || ''}"`
    ]);
    const csvContent = 'data:text/csv;charset=utf-8,\uFEFF' + [headers.join(','), ...rows.map(e => e.join(','))].join('\n');
    const encodedUri = encodeURI(csvContent);
    const link = document.createElement('a');
    link.setAttribute('href', encodedUri);
    link.setAttribute('download', `Bao_Cao_Inbound_${activeDate || 'HCM_HUB'}.csv`);
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
  };

  return (
    <div className="inbound-dashboard dashboard-container w-full max-w-7xl mx-auto pb-12 text-slate-100 font-sans">
      {/* Row 1: Header Control Block */}
      <header className="dashboard-header" style={{ position: 'relative', display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '14px 24px' }}>

        {/* LEFT: Sync Button + Logo */}
        <div style={{ display: 'flex', alignItems: 'center', gap: '14px', flexShrink: 0 }}>
          <button
            className="google-sync-btn"
            onClick={fetchAndUpdateData}
            disabled={loading}
            style={{ width: 'auto', padding: '10px 20px' }}
          >
            <span className="w-1.5 h-1.5 rounded-full bg-[#22c55e] animate-pulse shrink-0" style={{ marginRight: '8px' }} />
            {loading ? 'Đang đồng bộ...' : 'Đồng bộ'}
          </button>

          <img src="logo.png" alt="J&T Cargo Logo" className="jt-logo" style={{ height: '80px', borderRadius: '10px', display: 'block' }} />
        </div>

        {/* CENTER: Title — absolute center of header */}
        <div style={{ position: 'absolute', left: '50%', transform: 'translateX(-50%)', textAlign: 'center', pointerEvents: 'none' }}>
          <h1 style={{ fontSize: '36px', fontWeight: 900, color: '#fff', letterSpacing: '-0.5px', lineHeight: '1.1', textShadow: '0 2px 20px rgba(99,102,241,0.5)', margin: 0, whiteSpace: 'nowrap' }}>HCM HUB Inbound Dashboard </h1>
          <p className="subtitle text-xs text-slate-400" style={{ marginTop: '4px', textAlign: 'center', display: 'block' }}>Operational overview of today's inbound activities</p>
        </div>

        {/* RIGHT: Status + Export Button + Date Picker */}
        <div className="header-right" style={{ flexShrink: 0, display: 'flex', flexDirection: 'column', alignItems: 'flex-end', gap: '8px' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
            <button
              className="google-sync-btn"
              onClick={handleExportCSV}
              style={{
                width: 'auto',
                padding: '5px 14px',
                fontSize: '12px',
                background: '#092518',
                borderRadius: '20px',
                display: 'inline-flex',
                alignItems: 'center',
                gap: '6px'
              }}
              title="Xuất báo cáo Excel / CSV"
            >
              <i className="fa-solid fa-file-excel text-[#10b981]" style={{ fontSize: '13px' }}></i>
              Xuất Báo Cáo
            </button>
            <div style={{ 
              fontSize: '11px', 
              color: '#B8F7E4', 
              background: 'rgba(184, 247, 228, 0.05)', 
              border: '1px solid rgba(184, 247, 228, 0.2)', 
              padding: '4px 12px', 
              borderRadius: '20px', 
              fontWeight: 600, 
              fontFamily: "'Inter', sans-serif",
              display: 'flex',
              alignItems: 'center',
              gap: '6px',
              textShadow: '0 0 8px rgba(184,247,228,0.3)'
            }}>
              <span className="w-1.5 h-1.5 rounded-full bg-[#B8F7E4] animate-pulse" />
              Update: {lastUpdate || lastUpdateObj?.last_update || 'Đang cập nhật...'}
            </div>
          </div>
          <div className="date-control-wrapper flex items-center gap-2">
            <span className="control-label text-xs text-slate-400 font-semibold">Operations Date</span>
            <DatePicker
              selectedDate={activeDate}
              onDateChange={(d: string) => setSelectedInboundDate(d)}
              availableDates={inboundDates}
              align="right"
              className="w-[210px]"
              buttonClassName="!py-1.5 !px-4 !rounded-full text-xs font-bold"
            />
          </div>
        </div>
      </header>


      {/* Sync State Overlay */}
      {loading && (
        <div className="empty-state-overlay">
          <div className="empty-state-card">
            <div className="empty-icon-wrapper">
              <i className="fa-solid fa-circle-notch fa-spin"></i>
            </div>
            <h3>Đang đồng bộ dữ liệu...</h3>
            <p>Hệ thống đang tải dữ liệu thực tế từ Google Sheet...</p>
          </div>
        </div>
      )}

      {/* Row 1: KPI Cards with Thematic Border Tracing Glow */}
      <section className="kpi-grid">
        {/* KPI 1: Inbound (orders) */}
        <div className="kpi-card accent-green glass-card report-glow-card glow-cyan">
          <div className="kpi-card-header">
            <span className="kpi-title" style={{ color: "#B8F7E4" }}>Inbound (orders)</span>
            <i className="fa-solid fa-warehouse kpi-icon"></i>
          </div>
          <div className="kpi-card-body">
            <span className="kpi-value"><NumberTicker value={totalOrders} /></span>
            <span className="kpi-sub">Tổng đơn hàng đã nhập kho</span>
          </div>
          <div className="kpi-glow"></div>
        </div>

        {/* KPI 2: Inbound (weight) */}
        <div className="kpi-card accent-green glass-card report-glow-card glow-emerald">
          <div className="kpi-card-header">
            <span className="kpi-title">Inbound (weight)</span>
            <i className="fa-solid fa-weight-hanging kpi-icon"></i>
          </div>
          <div className="kpi-card-body">
            {/* weight_ton đã ở đơn vị TẤN từ backend (sync_postgre.py) — KHÔNG chia /1000
                nữa ở đây (trước đây chia lần 2 khiến số hiển thị sai 1000 lần). */}
            <span className="kpi-value"><NumberTicker value={totalWeight} decimals={1} /> Tấn</span>
            <span className="kpi-sub">Avg: {(totalOrders > 0 ? (totalWeight * 1000) / totalOrders : 0).toFixed(2)} kg/pkg</span>
          </div>
          <div className="kpi-glow"></div>
        </div>

        {/* KPI 3: Inbound Truck ETA - HCM HUB */}
        <div className="kpi-card accent-lime glass-card report-glow-card glow-amber">
          <div className="kpi-card-header">
            <span className="kpi-title">Inbound Truck ETA - HCM HUB</span>
            <i className="fa-solid fa-truck-fast kpi-icon"></i>
          </div>
          <div className="kpi-card-body" style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
            <span className="kpi-value"><NumberTicker value={totalTransitVehicles} /> xe</span>
            <div style={{ display: 'flex', flexDirection: 'column', gap: '2.5px', fontSize: '0.95rem', color: 'var(--text-secondary)', borderTop: '1px solid rgba(255,255,255,0.06)', paddingTop: '6px', marginTop: '4px' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                <span>Shuttle:</span>
                <strong style={{ color: '#a3e635' }}><NumberTicker value={totalShuttleVehicles} /> xe</strong>
              </div>
              <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                <span>Linehaul:</span>
                <strong style={{ color: '#f97316' }}><NumberTicker value={totalLinehaulVehicles} /> xe</strong>
              </div>
            </div>
          </div>
          <div className="kpi-glow"></div>
        </div>

        {/* KPI 4: Forecast */}
        <div className="kpi-card accent-orange glass-card report-glow-card glow-purple">
          <div className="kpi-card-header">
            <span className="kpi-title" style={{ fontSize: '1.08rem', fontWeight: 700, letterSpacing: '0.02em' }}>Forecast</span>
            <i className="fa-solid fa-chart-line kpi-icon"></i>
          </div>
          <div className="kpi-card-body" style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
            <div style={{ display: 'flex', alignItems: 'baseline', gap: '10px' }}>
              <span className="kpi-value"><NumberTicker value={totalForecast} /></span>
              <span style={{ fontSize: '1.08rem', color: '#E2E8F0', fontWeight: 700, letterSpacing: '0.01em' }}>({totalForecastWeight.toFixed(1).replace('.', ',')} Tấn)</span>
            </div>
            <div style={{ display: 'flex', flexDirection: 'column', gap: '4px', fontSize: '0.98rem', color: '#E2E8F0', borderTop: '1px solid rgba(255,255,255,0.08)', paddingTop: '6px', marginTop: '4px' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                <span style={{ fontWeight: 700, color: '#F1F5F9', fontSize: '0.98rem' }}>Shuttle:</span>
                <strong style={{ color: '#a3e635', fontSize: '1.18rem', fontWeight: 800 }}>
                  <NumberTicker value={finalShuttleForecast} /> <span style={{ fontSize: '0.9rem', color: '#CBD5E1', fontWeight: 600 }}>({finalShuttleWeight.toFixed(1).replace('.', ',')} Tấn)</span>
                </strong>
              </div>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                <span style={{ fontWeight: 700, color: '#F1F5F9', fontSize: '0.98rem' }}>Linehaul:</span>
                <strong style={{ color: '#f97316', fontSize: '1.18rem', fontWeight: 800 }}>
                  <NumberTicker value={finalLinehaulForecast} /> <span style={{ fontSize: '0.9rem', color: '#CBD5E1', fontWeight: 600 }}>({finalLinehaulWeight.toFixed(1).replace('.', ',')} Tấn)</span>
                </strong>
              </div>
            </div>
          </div>
          <div className="kpi-glow"></div>
        </div>
      </section>

      {/* Row 2: Charts */}
      <section className="charts-grid">
        {/* Line Chart */}
        <div className="chart-container-card dual-line-wrapper report-glow-card glow-cyan">
          <div className="chart-header">
            <h2 style={{ color: "#B8F7E4 !important" }}>Hourly Processing Trend</h2>
            <div className="chart-legend-custom">
              <span className="legend-item"><span className="dot orange"></span>Created</span>
              <span className="legend-item"><span className="dot blue"></span>Pickup Done</span>
              <span className="legend-item"><span className="dot green"></span>Transporting</span>
              <span className="legend-item"><span className="dot cyan"></span>Inbound</span>
            </div>
          </div>
          <div className="chart-canvas-wrapper">
            <canvas ref={canvasRef} id="hourlyTrendChart"></canvas>
          </div>
        </div>

        {/* Donut Chart */}
        <div className="chart-container-card donut-wrapper report-glow-card glow-emerald">
          <div className="chart-header">
            <h2 style={{ color: "#B8F7E4 !important" }}>Orders status</h2>
          </div>
          <div className="donut-chart-box">
            {/* SVG concentric arcs + centre label */}
            <div className="donut-canvas-container">
              <svg width="100%" height="100%" viewBox="0 0 200 200" style={{ transform: 'rotate(-90deg)', overflow: 'visible' }}>
                {renderedSegments.map((s) => {
                  const paths = [];
                  const baseRadii = [
                    { rIn: 38, rOut: 58, baseOpacity: 0.4 },
                    { rIn: 58, rOut: 78, baseOpacity: 0.7 },
                    { rIn: 78, rOut: 98, baseOpacity: 1.0 }
                  ];
                  
                  // Render layers up to s.layers
                  for (let i = 0; i < s.layers; i++) {
                    const { rIn, rOut, baseOpacity } = baseRadii[i];
                    const pathData = getSvgArcPath(100, 100, rIn, rOut, s.startAngle, s.endAngle);
                    
                    let opacity = baseOpacity;
                    if (hoveredStatus) {
                      opacity = hoveredStatus === s.name ? 1.0 : 0.15;
                    }

                    paths.push(
                      <motion.path
                        key={`${s.name}-layer-${i}`}
                        d={pathData}
                        fill={s.color}
                        opacity={opacity}
                        initial={{ pathLength: 0 }}
                        animate={{ pathLength: 1 }}
                        transition={{ duration: 1.0, ease: "easeOut", delay: i * 0.1 }}
                        style={{
                          cursor: 'pointer',
                          transformOrigin: '100px 100px',
                          transform: hoveredStatus === s.name ? 'scale(1.03)' : 'scale(1)',
                          transition: 'transform 0.25s cubic-bezier(0.4, 0, 0.2, 1), opacity 0.25s cubic-bezier(0.4, 0, 0.2, 1)'
                        }}
                        onMouseEnter={() => setHoveredStatus(s.name)}
                        onMouseLeave={() => setHoveredStatus(null)}
                      />
                    );
                  }
                  return <g key={s.name}>{paths}</g>;
                })}
              </svg>
              <div className="donut-center-text" style={{ transition: 'all 0.2s ease' }}>
                <span className="number">{activeDisplayStatus.pct}%</span>
                <span className="label" style={{ fontSize: '0.62rem' }}>{activeDisplayStatus.label}</span>
              </div>
            </div>
            {/* Legend stacked vertically */}
            <div className="donut-legend">
              <div 
                className="donut-legend-item"
                style={{ 
                  cursor: 'pointer',
                  opacity: hoveredStatus && hoveredStatus !== 'Inbound' ? 0.35 : 1,
                  transform: hoveredStatus === 'Inbound' ? 'translateX(4px)' : 'none',
                  transition: 'all 0.2s ease-in-out'
                }}
                onMouseEnter={() => setHoveredStatus('Inbound')}
                onMouseLeave={() => setHoveredStatus(null)}
              >
                <div className="donut-legend-dot" style={{ background: '#B8F7E4' }}></div>
                <div className="donut-legend-header">
                  <span className="label-text">Inbound</span>
                  <span className="donut-legend-pct" style={{ marginLeft: '4px' }}>({inboundPct}%)</span>
                </div>
                <span className="donut-legend-value">{totalInbound.toLocaleString()}</span>
              </div>

              <div 
                className="donut-legend-item"
                style={{ 
                  cursor: 'pointer',
                  opacity: hoveredStatus && hoveredStatus !== 'Transporting' ? 0.35 : 1,
                  transform: hoveredStatus === 'Transporting' ? 'translateX(4px)' : 'none',
                  transition: 'all 0.2s ease-in-out'
                }}
                onMouseEnter={() => setHoveredStatus('Transporting')}
                onMouseLeave={() => setHoveredStatus(null)}
              >
                <div className="donut-legend-dot" style={{ background: '#C8FF3D' }}></div>
                <div className="donut-legend-header">
                  <span className="label-text">Transporting</span>
                  <span className="donut-legend-pct" style={{ marginLeft: '4px' }}>({inTransitPct}%)</span>
                </div>
                <span className="donut-legend-value">{totalInTransit.toLocaleString()}</span>

              </div>

              <div 
                className="donut-legend-item"
                style={{ 
                  cursor: 'pointer',
                  opacity: hoveredStatus && hoveredStatus !== 'Pickup Done' ? 0.35 : 1,
                  transform: hoveredStatus === 'Pickup Done' ? 'translateX(4px)' : 'none',
                  transition: 'all 0.2s ease-in-out'
                }}
                onMouseEnter={() => setHoveredStatus('Pickup Done')}
                onMouseLeave={() => setHoveredStatus(null)}
              >
                <div className="donut-legend-dot" style={{ background: '#38BDF8' }}></div>
                <div className="donut-legend-header">
                  <span className="label-text">Pickup Done</span>
                  <span className="donut-legend-pct" style={{ marginLeft: '4px' }}>({pickupDonePct}%)</span>
                </div>
                <span className="donut-legend-value">{totalPickupDone.toLocaleString()}</span>
              </div>

              <div 
                className="donut-legend-item"
                style={{ 
                  cursor: 'pointer',
                  opacity: hoveredStatus && hoveredStatus !== 'Created' ? 0.35 : 1,
                  transform: hoveredStatus === 'Created' ? 'translateX(4px)' : 'none',
                  transition: 'all 0.2s ease-in-out'
                }}
                onMouseEnter={() => setHoveredStatus('Created')}
                onMouseLeave={() => setHoveredStatus(null)}
              >
                <div className="donut-legend-dot" style={{ background: '#FC6C26' }}></div>
                <div className="donut-legend-header">
                  <span className="label-text">Created</span>
                  <span className="donut-legend-pct" style={{ marginLeft: '4px' }}>({createdPct}%)</span>
                </div>
                <span className="donut-legend-value">{totalCreated.toLocaleString()}</span>
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* Row 3: Tables */}
      <section className="tables-grid">
        {/* Table 1: Origin Station Inbound */}
        <div className="table-container-card glass-card report-glow-card glow-cyan" style={{ display: 'flex', flexDirection: 'column' }}>
          <div className="table-header" style={{ padding: '10px 16px', borderBottom: '1px solid rgba(255,255,255,0.06)', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <h2 style={{ fontSize: '12px', fontWeight: 700, letterSpacing: '1.5px', textTransform: 'uppercase', color: '#B8F7E4', margin: 0 }}>Origin Station Inbound</h2>
            <span className="badge-count sky">{allSendingFCs.length} bưu cục</span>
          </div>
          <div className="table-wrapper" style={{ overflow: 'auto', maxHeight: '400px', position: 'relative' }}>
            <table className="premium-table">
              <thead style={{ position: 'sticky', top: 0, zIndex: 10 }}>
                <tr>
                  <th style={{ width: '50px' }}>#</th>
                  <th>BƯU CỤC</th>
                  <th style={{ textAlign: 'right' }}>Xe</th>
                  <th style={{ textAlign: 'right' }}>Inbound</th>
                  <th style={{ textAlign: 'right' }}>Trọng lượng (tấn)</th>
                  <th style={{ textAlign: 'right' }}>Tỉ lệ</th>
                </tr>
              </thead>
              <tbody>
                {allSendingFCs.length > 0 && (
                  <tr className="total-row" style={{ fontWeight: 'bold', position: 'sticky', top: '41px', background: 'rgba(56, 189, 248, 0.15)', color: '#38bdf8', zIndex: 9, backdropFilter: 'blur(8px)' }}>
                    <td className="table-index">-</td>
                    <td className="table-buucuc" style={{ color: '#38bdf8' }}>TỔNG CỘNG</td>
                    <td className="num-tabular" style={{ textAlign: 'right', color: '#38bdf8' }}>{totalSendingVehicles} xe</td>
                    <td className="num-tabular" style={{ textAlign: 'right', color: '#38bdf8' }}>{totalSendingOrders.toLocaleString()}</td>
                    <td className="num-tabular" style={{ textAlign: 'right', color: '#38bdf8' }}>{totalSendingWeight.toLocaleString(undefined, { minimumFractionDigits: 1, maximumFractionDigits: 1 })}</td>
                    <td className="num-tabular" style={{ textAlign: 'right', color: '#38bdf8' }}>100%</td>
                  </tr>
                )}
                {allSendingFCs.map((fc, idx) => (
                  <tr key={fc.fc}>
                    <td className="table-index">{idx + 1}</td>
                    <td className="table-buucuc">{fc.fc}</td>
                    <td className="num-tabular" style={{ textAlign: 'right' }}>
                      <span className="badge-count violet">{fc.vehicles} xe</span>
                    </td>
                    <td className="num-tabular" style={{ textAlign: 'right', color: '#10b981', fontWeight: 600 }}>{fc.orders.toLocaleString()}</td>
                    <td className="num-tabular" style={{ textAlign: 'right' }}>{fc.weight.toLocaleString(undefined, { minimumFractionDigits: 1, maximumFractionDigits: 1 })}</td>
                    <td className="num-tabular" style={{ textAlign: 'right', fontWeight: '600', color: '#38bdf8' }}>
                      {totalSendingOrders > 0 ? ((fc.orders / totalSendingOrders) * 100).toFixed(1) : '0.0'}%
                    </td>
                  </tr>
                ))}
                {allSendingFCs.length === 0 && (
                  <tr>
                    <td colSpan={6} style={{ textAlign: 'center', color: '#5a6578', padding: '24px' }}>Không có dữ liệu</td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </div>

        {/* Table 2: Xe đang di chuyển (Trucks in Transit) */}
        <div className="table-container-card glass-card report-glow-card glow-amber" style={{ display: 'flex', flexDirection: 'column' }}>
          <div className="table-header" style={{ padding: '10px 16px', borderBottom: '1px solid rgba(255,255,255,0.06)', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <h2 style={{ fontSize: '12px', fontWeight: 700, letterSpacing: '1.5px', textTransform: 'uppercase', color: '#B8F7E4', margin: 0 }}>Inbound Truck ETA - HCM HUB</h2>
            <span className="badge-count amber">{totalTransitVehicles} xe</span>
          </div>
          <div className="table-wrapper" style={{ overflow: 'auto', maxHeight: '400px', position: 'relative' }}>
            <table className="premium-table">
              <thead style={{ position: 'sticky', top: 0, zIndex: 10 }}>
                <tr>
                  <th style={{ width: '50px' }}>#</th>
                  <th>Station</th>
                  <th style={{ textAlign: 'left' }}>Trucking</th>
                  <th style={{ textAlign: 'right' }}>Orders</th>
                  <th style={{ textAlign: 'right' }}>Weight</th>
                  <th style={{ textAlign: 'center' }}>ETA</th>
                </tr>
              </thead>
              <tbody>
                {incomingVehicles.length > 0 && (
                  <tr className="total-row" style={{ fontWeight: 'bold', position: 'sticky', top: '41px', background: 'rgba(245, 158, 11, 0.15)', color: '#f59e0b', zIndex: 9, backdropFilter: 'blur(8px)' }}>
                    <td className="table-index">-</td>
                    <td className="table-buucuc" style={{ color: '#f59e0b' }}>TỔNG CỘNG</td>
                    <td className="table-buucuc" style={{ textAlign: 'left', color: '#f59e0b' }}>{totalTransitVehicles} xe</td>
                    <td className="num-tabular" style={{ textAlign: 'right', color: '#f59e0b' }}>
                      {incomingVehicles.reduce((a, b) => a + b.orders, 0).toLocaleString()}
                    </td>
                    <td className="num-tabular" style={{ textAlign: 'right', color: '#f59e0b' }}>
                      {(incomingVehicles.reduce((a, b) => a + b.weight, 0) >= 0.1
                        ? (incomingVehicles.reduce((a, b) => a + b.weight, 0)).toLocaleString(undefined, { minimumFractionDigits: 1, maximumFractionDigits: 1 })
                        : (incomingVehicles.reduce((a, b) => a + b.weight, 0)).toLocaleString(undefined, { minimumFractionDigits: 3, maximumFractionDigits: 3 })
                      )} tấn
                    </td>
                    <td style={{ textAlign: 'center', color: '#f59e0b' }}>-</td>
                  </tr>
                )}
                {incomingVehicles.map((v, idx) => (
                  <tr key={v.station + '-' + idx}>
                     <td className="table-index">{idx + 1}</td>
                     <td className="table-buucuc">{v.station}</td>
                     <td className="num-tabular" style={{ textAlign: 'left', color: '#38bdf8', fontWeight: 500 }}>{v.trucking} xe</td>
                     <td className="num-tabular" style={{ textAlign: 'right', color: '#f59e0b', fontWeight: 600 }}>{v.orders.toLocaleString()}</td>
                     <td className="num-tabular" style={{ textAlign: 'right', color: '#a78bfa' }}>
                       {(v.weight >= 0.1
                         ? (v.weight).toLocaleString(undefined, { minimumFractionDigits: 1, maximumFractionDigits: 1 })
                         : (v.weight).toLocaleString(undefined, { minimumFractionDigits: 3, maximumFractionDigits: 3 })
                       )} tấn
                     </td>
                     <td className="num-tabular" style={{ textAlign: 'center', color: '#64748b' }}>{v.eta ? v.eta : '--:--'}</td>
                  </tr>
                ))}
                {incomingVehicles.length === 0 && (
                  <tr>
                    <td colSpan={6} style={{ textAlign: 'center', color: '#5a6578', padding: '24px' }}>Không có xe đang di chuyển</td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </div>
      </section>



    </div>
  );
}