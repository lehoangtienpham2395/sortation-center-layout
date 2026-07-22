import { useState, useEffect, useRef } from 'react';
import { motion } from 'framer-motion';

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
  arrivalData: _arrivalData,
  truckEtaData,
  selectedInboundDate,
  setSelectedInboundDate,
  loading,
  fetchAndUpdateData,
  lastUpdate
}: InboundDashboardProps) {
  const [dateDropdownOpen, setDateDropdownOpen] = useState(false);
  const [hoveredStatus, setHoveredStatus] = useState<string | null>(null);
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const chartInstanceRef = useRef<any | null>(null);

  // 1. Extract and sort available dates (excluding future dates > today)
  const nowVN = new Date(new Date().toLocaleString('en-US', { timeZone: 'Asia/Ho_Chi_Minh' }));
  const padStr = (n: number) => String(n).padStart(2, '0');
  const todayOpDate = getOperatingDateFromTimestamp(
    `${nowVN.getFullYear()}-${padStr(nowVN.getMonth() + 1)}-${padStr(nowVN.getDate())} ${padStr(nowVN.getHours())}:${padStr(nowVN.getMinutes())}`
  );

  const rawInboundDates = Array.from(
    new Set([
      ...inboundData.map(d => d['Ngày vận hành_Inbound'] || d['Ngy vn hnh_Inbound']),
      ...inboundData.map(d => d['Ngày vận hành_Forecast'] || d['Ngy vn hnh_Forecast']),
      ...inboundData.map(d => d['Ngày vận hành_Pickup'] || d['Ngy vn hnh_Pickup']),
      ...inboundData.map(d => d['Ngày vận hành_Arrival'] || d['Ngy vn hnh_Arrival'])
    ].filter(Boolean))
  ) as string[];

  const inboundDates = rawInboundDates.filter(d => !todayOpDate || d <= todayOpDate);
  inboundDates.sort((a, b) => b.localeCompare(a));
  const activeDate = selectedInboundDate || inboundDates[0] || rawInboundDates[0] || '';

  // 2. Filter datasets by active date
  const getStatus = (d: any) => d['Trng thi'] || d['Trạng thái'];
  const getDateInbound = (d: any) => d['Ngy vn hnh_Inbound'] || d['Ngày vận hành_Inbound'];
  const getDateForecast = (d: any) => d['Ngy vn hnh_Forecast'] || d['Ngày vận hành_Forecast'];

  const filteredInbound = inboundData.filter(d => (getStatus(d) === 'Inbound') && getDateInbound(d) === activeDate);
  const filteredForecast = inboundData.filter(d => (getStatus(d) === 'Created') && getDateForecast(d) === activeDate && (d['Bu cc'] || d['Bưu cục'] || '').trim().toUpperCase() !== 'BN HUB');
  const filteredPickup = inboundData.filter(d => getStatus(d) === 'Pickup Done' && getDateForecast(d) === activeDate && (d['Bu cc'] || d['Bưu cục'] || '').trim().toUpperCase() !== 'BN HUB');
  const filteredTransporting = inboundData.filter(d => getStatus(d) === 'Transporting' && getDateForecast(d) === activeDate && (d['Bu cc'] || d['Bưu cục'] || '').trim().toUpperCase() !== 'BN HUB');
  const filteredChuaVeHub = [...filteredForecast, ...filteredPickup, ...filteredTransporting];

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
  const filteredLinehaul = linehaulData.filter(d => getLinehaulOperatingDate(d) === activeDate);

  // 3. Aggregate operational statistics

  let forecastRotHomTruoc = 0;
  let forecastRotHomNay = 0;

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

  [...filteredInbound, ...filteredChuaVeHub].forEach(d => {
    const status = d['Trng thi'] || d['Trạng thái'];
    const vol = parseInt(d['Volume'], 10) || 0;
    const wt = parseFloat(d['Weight']) || 0;
    const stageKey = stages[status] ? status : 'Created';
    stages[stageKey].orders += vol;
    stages[stageKey].weight += wt;
    // Chỉ cộng vào ordersWithWeight khi row này có dữ liệu weight thực tế
    if (wt > 0) {
      stagesWithWeight[stageKey] += vol;
    }
  });

  // Phân tách đơn Forecast cho toàn bộ dữ liệu (bảo đảm khớp số liệu BN HUB và tránh lệch lịch sử)
  inboundData.forEach(d => {
    const fcDate = d['Ngy vn hnh_Forecast'] || d['Ngày vận hành_Forecast'] || '';
    if (!fcDate) return;

    const station = (d['Bu cc'] || d['Bưu cục'] || '').trim().toUpperCase();
    const status = d['Trng thi'] || d['Trạng thái'];

    // Bỏ qua BN HUB khỏi Forecast (BN HUB không nằm trong kế hoạch sản lượng của các bưu cục)
    if (station === 'BN HUB') {
      return;
    }

    const vol = parseInt(d['Volume'], 10) || 0;

    if (fcDate === activeDate) {
      forecastRotHomNay += vol;
    } else if (fcDate < activeDate) {
      const ibDate = d['Ngy vn hnh_Inbound'] || d['Ngày vận hành_Inbound'] || '';
      // Nếu chưa nhập kho, hoặc nhập kho từ ngày activeDate trở đi -> đơn này vẫn là backlog chờ xử lý vào ngày activeDate
      if (status !== 'Inbound' || ibDate >= activeDate) {
        forecastRotHomTruoc += vol;
      }
    }
  });

  const filteredTruckEta = (truckEtaData || []).filter(d => {
    return (d['Ngy vn hnh'] || d['Ngày vận hành']) === activeDate;
  });

  let totalOrders = stages['Inbound'].orders;
  let totalWeight = stages['Inbound'].weight;
  // Số đơn có weight thực tế > 0 → dùng để tính avg chính xác
  const ordersWithWeight = stagesWithWeight['Inbound'];
  // Tổng Forecast gồm những đơn chưa pickup (Rớt hôm trước + Rớt hôm nay)
  const totalForecast = forecastRotHomTruoc + forecastRotHomNay;



  // Trucking in transit: map directly from filteredTruckEta and apply exclusions
  const NORTH_POST_OFFICES = new Set([
    'HN THANH XUÂN', 'HN SÓC SƠN', 'HN THUẬN AN', 'HN PHÚC THỌ', 'HN XUÂN ĐỈNH',
    'HN THƯỜNG TÍN', 'HN HOÀNG MAI', 'HD KINH MÔN', 'HY VĂN GIANG', 'HN NGỌC HỒI',
    'HN MỸ ĐỨC', 'HN ĐÔNG ANH', 'HN HÀ ĐÔNG', 'HN THANH TRÌ', 'HN THANH LIỆT',
    'HN HOÀI ĐỨC', 'HN MÊ LINH', 'HN AN KHÁNH', 'HN CẦU GIẤY', 'HN THANH OAI',
    'HN ĐỐNG ĐA', 'HN CHƯƠNG MỸ', 'HN CHÚC SƠN', 'HN HẠ BẰNG', 'HN HÁT MÔN',
    'HN LONG BIÊN', 'HN PHÚ XUYÊN', 'HN HÀ NAM', 'HN SƠN TÂY', 'HN NAM TỪ LIÊM',
    'HN PHÚ DIỄN', 'HN TÂY HỒ', 'HN VĨNH TUY', 'HN ỨNG HÒA'
  ]);

  const incomingVehicles = filteredTruckEta
    .filter(d => {
      const key = (d['Station'] || d['Pickup_station'] || '').trim();
      if (!key) return false;
      const cleanKey = key.toUpperCase();
      if (cleanKey !== 'BN HUB' && (NORTH_POST_OFFICES.has(cleanKey) || cleanKey.startsWith('HN ') || cleanKey.startsWith('HD ') || cleanKey.startsWith('HY '))) {
        return false;
      }
      return true;
    })
    .map(d => {
      const orders = parseInt(d['Orders'] || d['Tng s n'] || d['Tổng số đơn'] || d['Chua dn Hub'] || d['Chưa đến Hub'] || 0, 10);
      const weight = parseFloat(d['weight'] || d['package_charge_weight'] || 0);
      let truckingCount = 0;
      if (typeof d['Trucking'] === 'number') {
        truckingCount = d['Trucking'];
      } else if (d['Trucking']) {
        const val = String(d['Trucking']).trim();
        // Check if it's a number string
        if (/^\d+$/.test(val)) {
          truckingCount = parseInt(val, 10);
        } else if (val !== '' && val.toLowerCase() !== 'nan') {
          truckingCount = 1;
        }
      }
      return {
        station: d['Station'] || d['Pickup_station'] || '',
        trucking: truckingCount,
        orders: orders,
        weight: weight,
        eta: d['ETA'] || d['Last time'] || '',
        rank: ((d['Station'] || d['Pickup_station'] || '').trim().toUpperCase() === 'BN HUB') ? 'Linehaul' : (d['Rank'] || 'Shuttle'),
        // Backwards compatibility keys:
        chuaDenHub: orders,
        tongDon: orders,
        vehicles: truckingCount,
        lastTime: d['ETA'] || d['Last time'] || ''
      };
    })
    .filter(v => v.orders > 0)
    .sort((a, b) => b.orders - a.orders);

  // Split by Shuttle and Linehaul ranks
  const shuttleVehicles = incomingVehicles.filter(v => v.rank === 'Shuttle');
  const linehaulVehicles = incomingVehicles.filter(v => v.rank === 'Linehaul');

  // Counts of actual vehicles (having non-empty transfercodes)
  const totalShuttleVehicles = shuttleVehicles.reduce((sum, v) => sum + v.vehicles, 0);
  const totalLinehaulVehicles = linehaulVehicles.reduce((sum, v) => sum + v.vehicles, 0);

  // Orders status: tổng đơn chưa đến Hub = "Đang trên đường". 
  // Lấy trực tiếp tổng từ danh sách xe đang di chuyển (incomingVehicles) để bảo đảm 100% khớp số liệu.
  let totalInTransitOrders = incomingVehicles.reduce((sum, s) => sum + s.orders, 0);

  const totalTransitVehicles = totalShuttleVehicles + totalLinehaulVehicles;

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
    const station = (d['Bu cc'] || d['Bưu cục'] || '').trim().toUpperCase();
    if (station === 'BN HUB') return;

    const arrTime = d['Arrival Time'] || d['Arrival_time'] || '';
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
    const fcTime = d['Forecast Time'] || '';
    const fcDate = getOperatingDateFromTimestamp(fcTime);
    const opDate = d['Ngy vn hnh_Forecast'] || d['Ngày vận hành_Forecast'] || '';
    return opDate === activeDate || fcDate === activeDate;
  }).forEach(d => {
    const station = (d['Bu cc'] || d['Bưu cục'] || '').trim().toUpperCase();
    if (station === 'BN HUB') {
      return;
    }
    const fcTime = d['Forecast Time'] || '';
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

  // 3. Pickup Time (Shipper đã lấy): Hiển thị tất cả đơn có Ngày vận hành_Pickup khớp với activeDate (không phân biệt trạng thái hiện tại)
  inboundData.filter(d => (d['Ngy vn hnh_Pickup'] || d['Ngày vận hành_Pickup']) === activeDate).forEach(d => {
    const station = (d['Bu cc'] || d['Bưu cục'] || '').trim().toUpperCase();
    if (station === 'BN HUB') {
      return;
    }
    const pkTime = d['Pickup Time'] !== undefined && d['Pickup Time'] !== null && d['Pickup Time'] !== ''
      ? d['Pickup Time']
      : undefined;
    if (pkTime !== undefined) {
      const hrVal = getHourFromTimestamp(pkTime);
      if (hrVal >= 0 && hrVal < 24) {
        const hour = `${String(hrVal).padStart(2, '0')}:00`;
        if (hourlyPickup[hour] !== undefined) {
          hourlyPickup[hour] += parseInt(d['Volume'], 10) || 0;
        }
      }
    }
  });

  // 4. Inbound (Nhập kho HUB): Hiển thị các đơn nhập kho trong ngày activeDate
  filteredInbound.forEach(d => {
    const station = (d['Bu cc'] || d['Bưu cục'] || '').trim().toUpperCase();
    if (station === 'BN HUB') {
      return;
    }
    if ((d['Trng thi'] || d['Trạng thái']) === 'Inbound') {
      const ibTime = d['Inbound Hour'] !== undefined && d['Inbound Hour'] !== null && d['Inbound Hour'] !== '' 
        ? d['Inbound Hour'] 
        : d['Inbound Time'];
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

  const inboundTrendData  = labels.map(l => hourlyInbound[l]);
  const arrivedTrendData  = labels.map(l => hourlyArrived[l]);
  const forecastTrendData = labels.map(l => hourlyForecast[l]);
  const pickupTrendData   = labels.map(l => hourlyPickup[l]);

  const totalInbound = stages['Inbound'].orders;
  
  // Mapping chuẩn hóa: Lấy trực tiếp stages['Transporting'].orders để bảo đảm khớp 100% với Layout Master
  const totalInTransitVehiclesOrders = incomingVehicles.reduce((sum, s) => sum + s.orders, 0);
  totalInTransitOrders = Math.max(stages['Transporting'].orders, totalInTransitVehiclesOrders);
  
  const totalPickupDone = stages['Pickup Done'].orders;
  
  // Orders status: các trạng thái lấy Forecast làm hệ quy chiếu (100%)
  const totalBase = totalForecast > 0 ? totalForecast : (totalInbound + totalInTransitOrders + totalPickupDone + stages['Created'].orders);
  
  // Phần Created (chờ lấy hàng) = lượng còn lại của Forecast sau khi trừ Inbound, Transporting, Pickup Done
  const totalCreated = totalForecast > 0
    ? Math.max(0, totalForecast - totalInbound - totalInTransitOrders - totalPickupDone)
    : stages['Created'].orders;

  const pendingOrders = totalCreated; // for fallback UI components
  totalOrders = totalInbound; // reassign the early let
  totalWeight = stages['Inbound'].weight;

  let inboundPct   = totalBase > 0 ? Math.round((totalInbound           / totalBase) * 100) : 0;
  let inTransitPct = totalBase > 0 ? Math.round((totalInTransitOrders   / totalBase) * 100) : 0;
  let pickupDonePct= totalBase > 0 ? Math.round((totalPickupDone        / totalBase) * 100) : 0;
  
  // Bảo đảm cấu trúc dữ liệu: Nếu tổng % các bước đang xử lý vượt 100% (do dồn hàng linehaul), tự động scale tỷ lệ để không vỡ biểu đồ tròn
  const totalCompletedPct = inboundPct + inTransitPct + pickupDonePct;
  if (totalForecast > 0 && totalCompletedPct > 100) {
    const scale = 100 / totalCompletedPct;
    inboundPct = Math.round(inboundPct * scale);
    inTransitPct = Math.round(inTransitPct * scale);
    pickupDonePct = Math.round(pickupDonePct * scale);
  }
  
  const createdPct   = totalBase > 0 ? Math.max(0, 100 - (inboundPct + inTransitPct + pickupDonePct)) : 0;
  // const pendingPct   = createdPct;

  // Concentric radial chart configurations
  const segments = [
      { name: 'Inbound', value: totalInbound, pct: inboundPct, color: '#B8F7E4', label: 'Inbound' },
      { name: 'Transporting', value: totalInTransitOrders, pct: inTransitPct, color: '#C8FF3D', label: 'Transporting' },
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

  // MỞ RỘNG METRICS BƯU CỤC GỬI (Đầy đủ bưu cục, tính tổng xe, tổng đơn, tổng trọng lượng, tỉ lệ %)
  const fcMetrics: Record<string, { fc: string; vehicles: Set<string>; orders: number; weight: number }> = {};
  const getFC = (name: any) => {
    if (!name) return null;
    const clean = String(name).trim().toUpperCase();
    if (!clean) return null;
    if (!fcMetrics[clean]) {
      fcMetrics[clean] = { fc: String(name).trim(), vehicles: new Set(), orders: 0, weight: 0 };
    }
    return fcMetrics[clean];
  };

  filteredInbound.forEach(d => {
    const status = d['Trng thi'] || d['Trạng thái'];
    if (status === 'Inbound') {
      // Dùng 'BN HUB' cho đơn không có bưu cục gốc (hàng nội bộ HUB)
      const fcName = d['Bưu cục'] || d['Bu cc'] || 'BN HUB';
      const fc = getFC(fcName);
      if (fc) {
        fc.orders += parseInt(d['Volume'], 10) || 0;
        fc.weight += parseFloat(d['Weight']) || 0;
      }
    }
  });

  filteredLinehaul.forEach(d => {
    // nextNetworkName là bưu cục ĐÍCH của chuyến xe → chính là bưu cục "gửi hàng đến HUB"
    const fcName = d['nextNetworkName'] || '';
    if (fcName && d['Phiếu nhiệm vụ']) {
      // Nếu bưu cục này chưa xuất hiện trong fcMetrics (không có inbound scan), tạo mới
      const clean = fcName.trim().toUpperCase();
      if (!fcMetrics[clean]) {
        fcMetrics[clean] = { fc: fcName.trim(), vehicles: new Set(), orders: 0, weight: 0 };
      }
      fcMetrics[clean].vehicles.add(d['Phiếu nhiệm vụ']);
      // Nếu orders chưa được tính từ inbound scan, dùng unloadingBillPiece làm proxy
      if (fcMetrics[clean].orders === 0) {
        fcMetrics[clean].orders += parseInt(d['unloadingBillPiece'] as any, 10) || 0;
        fcMetrics[clean].weight += parseFloat(d['unloadingWeight'] as any) || 0;
      }
    }
  });

  // Hiển thị đầy đủ bưu cục (bỏ slice(0,10))
  const allSendingFCs = Object.values(fcMetrics)
    .map(item => ({
      fc: item.fc,
      vehicles: item.vehicles.size,
      orders: item.orders,
      weight: item.weight
    }))
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
                label: 'Pickup Volume',
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
  }, [activeDate, inboundData, linehaulData, totalOrders, totalInTransitOrders, pendingOrders, forecastTrendData, arrivedTrendData, pickupTrendData, inboundTrendData, truckEtaData]);

  const toggleDropdown = () => setDateDropdownOpen(!dateDropdownOpen);
  const selectPreset = (preset: 'today' | 'yesterday') => {
    if (inboundDates.length === 0) return;
    if (preset === 'today') {
      setSelectedInboundDate(inboundDates[0]);
    } else if (preset === 'yesterday' && inboundDates.length > 1) {
      setSelectedInboundDate(inboundDates[1]);
    }
    setDateDropdownOpen(false);
  };

  return (
    <div className="inbound-dashboard dashboard-container w-full max-w-7xl mx-auto pb-12 text-slate-100 font-sans">
      {/* 1. Header Control Block */}
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
          <h1 style={{ fontSize: '36px', fontWeight: 900, color: '#fff', letterSpacing: '-0.5px', lineHeight: '1.1', textShadow: '0 2px 20px rgba(99,102,241,0.5)', margin: 0, whiteSpace: 'nowrap' }}>HCM HUB Inbound Dashboard</h1>
          <p className="subtitle text-xs text-slate-400" style={{ marginTop: '4px', textAlign: 'center', display: 'block' }}>Operational overview of today's inbound activities</p>
        </div>

        {/* RIGHT: Status + Date Picker */}
        <div className="header-right" style={{ flexShrink: 0, display: 'flex', flexDirection: 'column', alignItems: 'flex-end', gap: '8px' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
            <div style={{ 
              fontSize: '11px', 
              color: '#B8F7E4', 
              background: 'rgba(184, 247, 228, 0.05)', 
              border: '1px solid rgba(184, 247, 228, 0.2)', 
              padding: '5px 12px', 
              borderRadius: '20px', 
              fontWeight: 600, 
              fontFamily: "'Inter', sans-serif",
              display: 'flex',
              alignItems: 'center',
              gap: '6px',
              textShadow: '0 0 8px rgba(184,247,228,0.3)'
            }}>
              <span className="w-1.5 h-1.5 rounded-full bg-[#B8F7E4] animate-pulse" />
              Update: {lastUpdate || '...'}
            </div>
          </div>
          <div className="date-control-wrapper">
            <span className="control-label">Operations Date</span>
            <div className={`custom-datepicker ${dateDropdownOpen ? 'open' : ''}`}>
              <button className="datepicker-trigger" onClick={toggleDropdown}>
                <i className="fa-regular fa-calendar-days icon-cal" style={{ marginRight: '6px' }}></i>
                <span>{activeDate || 'Chọn ngày'}</span>
                <i className="fa-solid fa-chevron-down icon-arrow" style={{ marginLeft: '6px' }}></i>
              </button>
              {dateDropdownOpen && (
                <div className="datepicker-dropdown">
                  <div className="datepicker-presets">
                    <button className="preset-btn" onClick={() => selectPreset('today')}>Hôm nay</button>
                    <button className="preset-btn" onClick={() => selectPreset('yesterday')}>Hôm qua</button>
                  </div>
                  <div className="datepicker-list-header">Chọn ngày vận hành (30 ngày gần đây)</div>
                  <div className="datepicker-list">
                    {inboundDates.map(d => (
                      <button
                        key={d}
                        className={`datepicker-item ${d === activeDate ? 'active' : ''}`}
                        onClick={() => {
                          setSelectedInboundDate(d);
                          setDateDropdownOpen(false);
                        }}
                      >
                        {d}
                      </button>
                    ))}
                  </div>
                </div>
              )}
            </div>
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

      {/* Row 1: KPI Cards */}
      <section className="kpi-grid">
        {/* KPI 1: Inbound (orders) */}
        <div className="kpi-card accent-green glass-card">
          <div className="kpi-card-header">
            <span className="kpi-title">Inbound (orders)</span>
            <i className="fa-solid fa-warehouse kpi-icon"></i>
          </div>
          <div className="kpi-card-body">
            <span className="kpi-value"><NumberTicker value={totalOrders} /></span>
            <span className="kpi-sub">Tổng đơn hàng đã nhập kho</span>
          </div>
          <div className="kpi-glow"></div>
        </div>

        {/* KPI 2: Inbound (weight) */}
        <div className="kpi-card accent-green glass-card">
          <div className="kpi-card-header">
            <span className="kpi-title">Inbound (weight)</span>
            <i className="fa-solid fa-weight-hanging kpi-icon"></i>
          </div>
          <div className="kpi-card-body">
            <span className="kpi-value"><NumberTicker value={totalWeight / 1000} decimals={2} /> Tấn</span>
            <span className="kpi-sub">Avg: {(ordersWithWeight > 0 ? totalWeight / ordersWithWeight : 0).toFixed(2)} kg/pkg</span>
          </div>
          <div className="kpi-glow"></div>
        </div>

        {/* KPI 3: Inbound Truck ETA - HCM HUB */}
        <div className="kpi-card accent-lime glass-card">
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
        <div className="kpi-card accent-orange glass-card">
          <div className="kpi-card-header">
            <span className="kpi-title">Forecast</span>
            <i className="fa-solid fa-chart-line kpi-icon"></i>
          </div>
          <div className="kpi-card-body" style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
            <span className="kpi-value"><NumberTicker value={totalForecast} /></span>
            <div style={{ display: 'flex', flexDirection: 'column', gap: '4px', fontSize: '0.95rem', color: 'var(--text-secondary)', borderTop: '1px solid rgba(255,255,255,0.06)', paddingTop: '6px', marginTop: '4px' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                <span>Rớt hôm trước:</span>
                <strong style={{ color: '#FC6C26', fontSize: '1.1rem' }}><NumberTicker value={forecastRotHomTruoc} /></strong>
              </div>
              <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                <span>Rớt hôm nay:</span>
                <strong style={{ color: '#ffa066', fontSize: '1.1rem' }}><NumberTicker value={forecastRotHomNay} /></strong>
              </div>
            </div>
          </div>
          <div className="kpi-glow"></div>
        </div>
      </section>

      {/* Row 2: Charts */}
      <section className="charts-grid">
        {/* Line Chart */}
        <div className="chart-container-card dual-line-wrapper">
          <div className="chart-header">
            <h2>Hourly Processing Trend</h2>
            <div className="chart-legend-custom">
              <span className="legend-item"><span className="dot orange"></span>Created</span>
              <span className="legend-item"><span className="dot blue"></span>Pickup Volume</span>
              <span className="legend-item"><span className="dot green"></span>Transporting</span>
              <span className="legend-item"><span className="dot cyan"></span>Inbound</span>
            </div>
          </div>
          <div className="chart-canvas-wrapper">
            <canvas ref={canvasRef} id="hourlyTrendChart"></canvas>
          </div>
        </div>

        {/* Donut Chart */}
        <div className="chart-container-card donut-wrapper">
          <div className="chart-header">
            <h2>Orders status</h2>
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
                <span className="donut-legend-value">{totalInTransitOrders.toLocaleString()}</span>
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
        <div className="table-container-card glass-card" style={{ display: 'flex', flexDirection: 'column' }}>
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
                    <td className="num-tabular" style={{ textAlign: 'right', color: '#38bdf8' }}>{(totalSendingWeight / 1000).toLocaleString(undefined, { minimumFractionDigits: 3, maximumFractionDigits: 3 })}</td>
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
                    <td className="num-tabular" style={{ textAlign: 'right' }}>{(fc.weight / 1000).toLocaleString(undefined, { minimumFractionDigits: 3, maximumFractionDigits: 3 })}</td>
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
        <div className="table-container-card glass-card" style={{ display: 'flex', flexDirection: 'column' }}>
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
                      {(incomingVehicles.reduce((a, b) => a + b.weight, 0) / 1000).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })} tấn
                    </td>
                    <td style={{ textAlign: 'center', color: '#f59e0b' }}>-</td>
                  </tr>
                )}
                {incomingVehicles.map((v, idx) => (
                  <tr key={v.station + '-' + v.trucking}>
                     <td className="table-index">{idx + 1}</td>
                     <td className="table-buucuc">{v.station}</td>
                     <td className="num-tabular" style={{ textAlign: 'left', color: '#38bdf8', fontWeight: 500 }}>{v.trucking} xe</td>
                     <td className="num-tabular" style={{ textAlign: 'right', color: '#f59e0b', fontWeight: 600 }}>{v.orders.toLocaleString()}</td>
                     <td className="num-tabular" style={{ textAlign: 'right', color: '#a78bfa' }}>{(v.weight / 1000).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })} tấn</td>
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
