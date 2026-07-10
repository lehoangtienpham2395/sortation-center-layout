import { useState, useEffect, useRef } from 'react';

interface InboundDashboardProps {
  inboundData: any[];
  linehaulData: any[];
  arrivalData: any[];
  selectedInboundDate: string;
  setSelectedInboundDate: (date: string) => void;
  loading: boolean;
  fetchAndUpdateData: () => void;
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
  selectedInboundDate,
  setSelectedInboundDate,
  loading,
  fetchAndUpdateData
}: InboundDashboardProps) {
  const [dateDropdownOpen, setDateDropdownOpen] = useState(false);
  const [hoveredStatus, setHoveredStatus] = useState<string | null>(null);
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const chartInstanceRef = useRef<any | null>(null);

  // 1. Extract and sort available dates
  const inboundDates = Array.from(
    new Set([
      ...inboundData.map(d => d['Ngày vận hành_Inbound']),
      ...inboundData.map(d => d['Ngày vận hành_Forecast']),
      ...inboundData.map(d => d['Ngày vận hành_Pickup'])
    ].filter(Boolean))
  ) as string[];
  inboundDates.sort((a, b) => b.localeCompare(a));
  const activeDate = selectedInboundDate || inboundDates[0] || '';

  // 2. Filter datasets by active date
  const filteredInbound = inboundData.filter(d => (d['Trạng thái'] === 'Đã về Hub' || d['Trạng thái'] === 'Đã nhập hàng') && d['Ngày vận hành_Inbound'] === activeDate);
  const filteredForecast = inboundData.filter(d => (d['Trạng thái'] === 'Forecast' || d['Trạng thái'] === 'Điều phối bưu cục') && d['Ngày vận hành_Forecast'] === activeDate);
  const filteredPickup = inboundData.filter(d => d['Trạng thái'] === 'Lấy hàng thành công' && d['Ngày vận hành_Pickup'] === activeDate);
  const filteredChuaVeHub = [...filteredForecast, ...filteredPickup];

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

  const stages = {
    'Chưa về Hub': { orders: 0, weight: 0 },
    'Đã về Hub': { orders: 0, weight: 0 }
  };

  [...filteredInbound, ...filteredChuaVeHub].forEach(d => {
    const status = d['Trạng thái'];
    const vol = parseInt(d['Volume'], 10) || 0;
    const wt = parseFloat(d['Weight']) || 0;
    if (status === 'Đã về Hub' || status === 'Đã nhập hàng') {
      stages['Đã về Hub'].orders += vol;
      stages['Đã về Hub'].weight += wt;
    } else {
      stages['Chưa về Hub'].orders += vol;
      stages['Chưa về Hub'].weight += wt;
    }

    // Phân tách đơn Forecast cho toàn bộ đơn (bao gồm cả đã về và chưa về Hub) sử dụng cột Loại rớt từ backend
    const loaiRot = d['Loại rớt'] || '';
    if (loaiRot === 'Rớt hôm trước') {
      forecastRotHomTruoc += vol;
    } else if (loaiRot === 'Rớt hôm nay') {
      forecastRotHomNay += vol;
    }
  });

  // --- Arrival data (from the new Arrival Google Sheet) ---
  // Filter by active date
  const filteredArrival = arrivalData.filter(d => d['Ngày vận hành'] === activeDate);

  const totalOrders = stages['Đã về Hub'].orders;
  const totalWeight = stages['Đã về Hub'].weight;
  // Tổng Forecast gồm Đã về Hub + Chưa về Hub (cả cũ và mới)
  const totalForecast = stages['Đã về Hub'].orders + stages['Chưa về Hub'].orders;

  // KPI: số bưu cục đang trên đường (distinct Pickup_station với Chưa đến Hub > 0)
  const totalVehicles = new Set(
    filteredArrival
      .filter(d => (parseInt(d['Chưa đến Hub'], 10) || 0) > 0)
      .map(d => d['Pickup_station'])
      .filter(Boolean)
  ).size;

  // Orders status: tổng đơn chưa đến Hub = "Đang trên đường"
  const totalInTransitOrders = filteredArrival.reduce(
    (sum, d) => sum + (parseInt(d['Chưa đến Hub'], 10) || 0), 0
  );

  // Trucking in transit table: top 10 bưu cục Chưa đến Hub nhiều nhất
  const stationMap: Record<string, { station: string; chuaDenHub: number; tongDon: number; lastTime: string }> = {};
  filteredArrival.forEach(d => {
    const key = (d['Pickup_station'] || '').trim();
    if (!key) return;
    if (!stationMap[key]) {
      stationMap[key] = { station: key, chuaDenHub: 0, tongDon: 0, lastTime: '' };
    }
    stationMap[key].chuaDenHub += parseInt(d['Chưa đến Hub'], 10) || 0;
    stationMap[key].tongDon   += parseInt(d['Tổng số đơn'], 10) || 0;
    const lt = d['Last time'] || '';
    if (lt > stationMap[key].lastTime) stationMap[key].lastTime = lt;
  });

  const incomingVehicles = Object.values(stationMap)
    .filter(s => s.chuaDenHub > 0)
    .sort((a, b) => b.chuaDenHub - a.chuaDenHub);

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

  // 1. Trên đường về (Arrived) hourly: từ Arrival sheet, sum Tổng số đơn theo Scan Hour (Loại bỏ BN HUB để tránh lệch giờ)
  filteredArrival.forEach(d => {
    const station = (d['Pickup_station'] || '').trim().toUpperCase();
    if (station.includes('BN HUB') || station.includes('HCM004H')) return;

    const hr = d['Scan Hour'] !== undefined && d['Scan Hour'] !== null && d['Scan Hour'] !== ''
      ? d['Scan Hour']
      : (d['Last time'] ? d['Last time'].split(' ')[1]?.split(':')[0] : undefined);
    if (hr !== undefined && hr !== null && hr !== '') {
      const hrVal = parseInt(String(hr), 10);
      if (!isNaN(hrVal) && hrVal >= 0 && hrVal < 24) {
        const hour = `${String(hrVal).padStart(2, '0')}:00`;
        if (hourlyArrived[hour] !== undefined) {
          hourlyArrived[hour] += parseInt(d['Tổng số đơn'], 10) || 0;
        }
      }
    }
  });

  // 2. Forecast Time (Dự báo - Kế hoạch lấy): Hiển thị tất cả đơn có Ngày vận hành_Forecast khớp với activeDate (không phân biệt trạng thái hiện tại)
  inboundData.filter(d => d['Ngày vận hành_Forecast'] === activeDate).forEach(d => {
    const loaiRot = d['Loại rớt'] || '';
    if (loaiRot !== 'Rớt hôm trước') {
      const fcTime = d['Forecast Time'] !== undefined && d['Forecast Time'] !== null && d['Forecast Time'] !== ''
        ? d['Forecast Time']
        : undefined;
      if (fcTime !== undefined) {
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
  inboundData.filter(d => d['Ngày vận hành_Pickup'] === activeDate).forEach(d => {
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
    if (d['Trạng thái'] === 'Đã về Hub' || d['Trạng thái'] === 'Đã nhập hàng') {
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

  const pendingOrders = totalForecast;

  // Tính tỷ lệ % cho 3 trạng thái của Orders status doughnut chart
  const totalStates = totalOrders + totalInTransitOrders + pendingOrders;
  const inboundPct = totalStates > 0 ? Math.round((totalOrders / totalStates) * 100) : 0;
  const inTransitPct = totalStates > 0 ? Math.round((totalInTransitOrders / totalStates) * 100) : 0;
  const pendingPct = totalStates > 0 ? Math.max(0, 100 - inboundPct - inTransitPct) : 0;

  // Concentric radial chart configurations
  const segments = [
    { name: 'Đã nhập kho', value: totalOrders, pct: inboundPct, color: '#B8F7E4', label: 'Inbound' },
    { name: 'Đang trên đường', value: totalInTransitOrders, pct: inTransitPct, color: '#C8FF3D', label: 'In Transit' },
    { name: 'Chờ xử lý', value: pendingOrders, pct: pendingPct, color: '#FC6C26', label: 'Pending' }
  ];

  const activeSegments = segments.filter(s => s.pct > 0);
  const sortedSegments = [...activeSegments].sort((a, b) => b.pct - a.pct);

  const segmentLayers = new Map<string, number>();
  sortedSegments.forEach((s, index) => {
    if (index === 0) segmentLayers.set(s.name, 3);
    else if (index === 1) segmentLayers.set(s.name, 2);
    else segmentLayers.set(s.name, 1);
  });

  const gapAngle = 0.05; // ~3 degrees
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

  const highestStatus = sortedSegments[0] || segments[0] || { name: 'Đã nhập kho', value: 0, pct: 0, color: '#B8F7E4', label: 'Inbound' };
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
    if (d['Trạng thái'] === 'Đã về Hub' || d['Trạng thái'] === 'Đã nhập hàng') {
      const fc = getFC(d['Bưu cục']);
      if (fc) {
        fc.orders += parseInt(d['Volume'], 10) || 0;
        fc.weight += parseFloat(d['Weight']) || 0;
      }
    }
  });

  filteredLinehaul.forEach(d => {
    const fcName = d['nextNetworkName'] || '';
    if (fcName && d['Phiếu nhiệm vụ']) {
      const fc = getFC(fcName);
      if (fc) {
        fc.vehicles.add(d['Phiếu nhiệm vụ']);
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
                label: 'Dự báo (Forecast)',
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
                label: 'Shipper đã lấy (Actual Pickup)',
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
                label: 'Trên đường về (Arrived)',
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
                label: 'Nhập (Inbound)',
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
                grid: { color: 'rgba(139, 92, 246, 0.05)' },
                ticks: { color: '#a0aec0', font: { size: 9 } }
              },
              y: {
                grid: { color: 'rgba(139, 92, 246, 0.05)' },
                ticks: { color: '#a0aec0', font: { size: 9 } }
              }
            }
          }
        });
      }
    }
  }, [activeDate, inboundData, linehaulData, totalOrders, totalInTransitOrders, pendingOrders, forecastTrendData, arrivedTrendData, pickupTrendData, inboundTrendData]);

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
      <header className="dashboard-header">
        <div className="header-left">
          <div className="logo-container">
            <img src="logo.png" alt="J&T Cargo Logo" className="jt-logo" style={{ height: '36px', borderRadius: '6px', display: 'block' }} />
          </div>
          <div className="title-container">
            <h1 className="text-[20px] font-bold text-white tracking-tight">HCM HUB Inbound Dashboard</h1>
            <p className="subtitle text-xs text-slate-400">Operational overview of today's inbound activities</p>
          </div>
        </div>
        <div className="header-right">
          <div className="system-status">
            <span className="status-dot pulsing"></span>
            <span className="status-text">Update: {new Date().toLocaleString('vi-VN')}</span>
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
                        className={`datepicker-list-item ${d === activeDate ? 'active' : ''}`}
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
        <div className="kpi-card accent-green">
          <div className="kpi-card-header">
            <span className="kpi-title">Inbound (orders)</span>
            <i className="fa-solid fa-warehouse kpi-icon"></i>
          </div>
          <div className="kpi-card-body">
            <span className="kpi-value">{totalOrders.toLocaleString()}</span>
            <span className="kpi-sub">Tổng đơn hàng đã nhập kho</span>
          </div>
          <div className="kpi-glow"></div>
        </div>

        {/* KPI 2: Inbound (weight) */}
        <div className="kpi-card accent-green">
          <div className="kpi-card-header">
            <span className="kpi-title">Inbound (weight)</span>
            <i className="fa-solid fa-weight-hanging kpi-icon"></i>
          </div>
          <div className="kpi-card-body">
            <span className="kpi-value">{totalWeight.toLocaleString()} kg</span>
            <span className="kpi-sub">Avg: {(totalOrders > 0 ? totalWeight / totalOrders : 0).toFixed(2)} kg/pkg</span>
          </div>
          <div className="kpi-glow"></div>
        </div>

        {/* KPI 3: Trucking in Transit */}
        <div className="kpi-card accent-lime">
          <div className="kpi-card-header">
            <span className="kpi-title">Trucking in transit</span>
            <i className="fa-solid fa-truck-fast kpi-icon"></i>
          </div>
          <div className="kpi-card-body">
            <span className="kpi-value">{totalVehicles.toLocaleString()}</span>
            <span className="kpi-sub">Tổng lượng xe sắp về HUB</span>
          </div>
          <div className="kpi-glow"></div>
        </div>

        {/* KPI 4: Forecast */}
        <div className="kpi-card accent-orange">
          <div className="kpi-card-header">
            <span className="kpi-title">Forecast</span>
            <i className="fa-solid fa-chart-line kpi-icon"></i>
          </div>
          <div className="kpi-card-body" style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
            <span className="kpi-value">{totalForecast.toLocaleString()}</span>
            <div style={{ display: 'flex', flexDirection: 'column', gap: '4px', fontSize: '0.95rem', color: 'var(--text-secondary)', borderTop: '1px solid rgba(255,255,255,0.06)', paddingTop: '6px', marginTop: '4px' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                <span>Rớt hôm trước:</span>
                <strong style={{ color: '#FC6C26', fontSize: '1.1rem' }}>{forecastRotHomTruoc.toLocaleString()}</strong>
              </div>
              <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                <span>Rớt hôm nay:</span>
                <strong style={{ color: '#ffa066', fontSize: '1.1rem' }}>{forecastRotHomNay.toLocaleString()}</strong>
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
            <h2>Forecast/Arrived/Inbound trend hourly</h2>
            <div className="chart-legend-custom">
              <span className="legend-item"><span className="dot orange"></span>Dự báo (Forecast)</span>
              <span className="legend-item"><span className="dot blue"></span>Shipper đã lấy (Actual Pickup)</span>
              <span className="legend-item"><span className="dot green"></span>Trên đường về (Arrived)</span>
              <span className="legend-item"><span className="dot cyan"></span>Nhập (Inbound)</span>
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
                    { rIn: 42, rOut: 60, baseOpacity: 0.4 },
                    { rIn: 61, rOut: 79, baseOpacity: 0.7 },
                    { rIn: 80, rOut: 98, baseOpacity: 1.0 }
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
                      <path
                        key={`${s.name}-layer-${i}`}
                        d={pathData}
                        fill={s.color}
                        opacity={opacity}
                        style={{
                          transition: 'all 0.25s cubic-bezier(0.4, 0, 0.2, 1)',
                          cursor: 'pointer',
                          transformOrigin: '100px 100px',
                          transform: hoveredStatus === s.name ? 'scale(1.03)' : 'scale(1)'
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
                  opacity: hoveredStatus && hoveredStatus !== 'Đã nhập kho' ? 0.35 : 1,
                  transform: hoveredStatus === 'Đã nhập kho' ? 'translateX(4px)' : 'none',
                  transition: 'all 0.2s ease-in-out'
                }}
                onMouseEnter={() => setHoveredStatus('Đã nhập kho')}
                onMouseLeave={() => setHoveredStatus(null)}
              >
                <div className="donut-legend-dot" style={{ background: '#B8F7E4' }}></div>
                <div className="donut-legend-header">
                  <span className="label-text">Đã nhập kho</span>
                  <span className="donut-legend-pct" style={{ marginLeft: '4px' }}>({inboundPct}%)</span>
                </div>
                <span className="donut-legend-value">{totalOrders.toLocaleString()}</span>
              </div>
              <div 
                className="donut-legend-item"
                style={{ 
                  cursor: 'pointer',
                  opacity: hoveredStatus && hoveredStatus !== 'Đang trên đường' ? 0.35 : 1,
                  transform: hoveredStatus === 'Đang trên đường' ? 'translateX(4px)' : 'none',
                  transition: 'all 0.2s ease-in-out'
                }}
                onMouseEnter={() => setHoveredStatus('Đang trên đường')}
                onMouseLeave={() => setHoveredStatus(null)}
              >
                <div className="donut-legend-dot" style={{ background: '#C8FF3D' }}></div>
                <div className="donut-legend-header">
                  <span className="label-text">Đang trên đường</span>
                  <span className="donut-legend-pct" style={{ marginLeft: '4px' }}>({inTransitPct}%)</span>
                </div>
                <span className="donut-legend-value">{totalInTransitOrders.toLocaleString()}</span>
              </div>
              <div 
                className="donut-legend-item"
                style={{ 
                  cursor: 'pointer',
                  opacity: hoveredStatus && hoveredStatus !== 'Chờ xử lý' ? 0.35 : 1,
                  transform: hoveredStatus === 'Chờ xử lý' ? 'translateX(4px)' : 'none',
                  transition: 'all 0.2s ease-in-out'
                }}
                onMouseEnter={() => setHoveredStatus('Chờ xử lý')}
                onMouseLeave={() => setHoveredStatus(null)}
              >
                <div className="donut-legend-dot" style={{ background: '#FC6C26' }}></div>
                <div className="donut-legend-header">
                  <span className="label-text">Chờ xử lý</span>
                  <span className="donut-legend-pct" style={{ marginLeft: '4px' }}>({pendingPct}%)</span>
                </div>
                <span className="donut-legend-value">{pendingOrders.toLocaleString()}</span>
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* Row 3: Tables */}
      <section className="tables-grid">
        {/* Table 1: Origin Station Inbound */}
        <div className="table-container-card">
          <div className="table-header">
            <h2>Origin Station Inbound ({allSendingFCs.length})</h2>
          </div>
          <div className="table-wrapper" style={{ overflowY: 'auto', maxHeight: '400px', position: 'relative' }}>
            <table style={{ borderCollapse: 'collapse', width: '100%' }}>
              <thead style={{ position: 'sticky', top: 0, background: 'var(--panel-bg)', zIndex: 10 }}>
                <tr>
                  <th style={{ width: '40px', background: '#1e293b', color: '#94a3b8' }}>#</th>
                  <th style={{ background: '#1e293b', color: '#94a3b8' }}>Bưu cục gửi</th>
                  <th style={{ textAlign: 'right', background: '#1e293b', color: '#94a3b8' }}>Số xe</th>
                  <th style={{ textAlign: 'right', background: '#1e293b', color: '#94a3b8' }}>Số lượng Inbound</th>
                  <th style={{ textAlign: 'right', background: '#1e293b', color: '#94a3b8' }}>Trọng lượng (kg)</th>
                  <th style={{ textAlign: 'right', background: '#1e293b', color: '#94a3b8' }}>Tỉ lệ (%)</th>
                </tr>
              </thead>
              <tbody>
                {allSendingFCs.length > 0 && (
                  <tr style={{ fontWeight: 'bold', position: 'sticky', top: '35px', background: '#38bdf8', color: '#ffffff', zIndex: 9, borderBottom: '2px solid #0284c7' }}>
                    <td style={{ color: '#ffffff' }}>-</td>
                    <td style={{ color: '#ffffff' }}>TỔNG CỘNG ({allSendingFCs.length})</td>
                    <td style={{ textAlign: 'right', color: '#ffffff' }}>{totalSendingVehicles} xe</td>
                    <td style={{ textAlign: 'right', color: '#ffffff' }}>{totalSendingOrders.toLocaleString()}</td>
                    <td style={{ textAlign: 'right', color: '#ffffff' }}>{totalSendingWeight.toLocaleString()}</td>
                    <td style={{ textAlign: 'right', color: '#ffffff' }}>100%</td>
                  </tr>
                )}
                {allSendingFCs.map((fc, idx) => (
                  <tr key={fc.fc}>
                    <td className="highlight-val">{idx + 1}</td>
                    <td className="highlight-val">{fc.fc}</td>
                    <td className="highlight-purple" style={{ textAlign: 'right' }}>{fc.vehicles} xe</td>
                    <td className="highlight-green" style={{ textAlign: 'right' }}>{fc.orders.toLocaleString()}</td>
                    <td style={{ textAlign: 'right' }}>{fc.weight.toLocaleString()}</td>
                    <td style={{ textAlign: 'right', fontWeight: '600' }}>
                      {totalSendingOrders > 0 ? ((fc.orders / totalSendingOrders) * 100).toFixed(1) : '0.0'}%
                    </td>
                  </tr>
                ))}
                {allSendingFCs.length === 0 && (
                  <tr>
                    <td colSpan={6} style={{ textAlign: 'center', color: '#5a6578', padding: '20px' }}>Không có dữ liệu</td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </div>

        {/* Table 2: Trucking in Transit */}
        <div className="table-container-card">
          <div className="table-header">
            <h2>Trucking in transit ({incomingVehicles.length})</h2>
          </div>
          <div className="table-wrapper" style={{ overflowY: 'auto', maxHeight: '400px', position: 'relative' }}>
            <table style={{ borderCollapse: 'collapse', width: '100%' }}>
              <thead style={{ position: 'sticky', top: 0, background: 'var(--panel-bg)', zIndex: 10 }}>
                <tr>
                  <th style={{ width: '40px', background: '#1e293b', color: '#94a3b8' }}>#</th>
                  <th style={{ background: '#1e293b', color: '#94a3b8' }}>Bưu cục</th>
                  <th style={{ textAlign: 'right', background: '#1e293b', color: '#94a3b8' }}>Chưa đến Hub</th>
                  <th style={{ textAlign: 'right', background: '#1e293b', color: '#94a3b8' }}>Đã đến Hub</th>
                  <th style={{ textAlign: 'right', background: '#1e293b', color: '#94a3b8' }}>Tổng đơn</th>
                  <th style={{ textAlign: 'center', background: '#1e293b', color: '#94a3b8' }}>Cập nhật lúc</th>
                </tr>
              </thead>
              <tbody>
                {incomingVehicles.length > 0 && (
                  <tr style={{ fontWeight: 'bold', position: 'sticky', top: '35px', background: '#38bdf8', color: '#ffffff', zIndex: 9, borderBottom: '2px solid #0284c7' }}>
                    <td style={{ color: '#ffffff' }}>-</td>
                    <td style={{ color: '#ffffff' }}>TỔNG CỘNG ({incomingVehicles.length})</td>
                    <td style={{ textAlign: 'right', color: '#ffffff' }}>
                      {incomingVehicles.reduce((a, b) => a + b.chuaDenHub, 0).toLocaleString()}
                    </td>
                    <td style={{ textAlign: 'right', color: '#ffffff' }}>
                      {incomingVehicles.reduce((a, b) => a + (b.tongDon - b.chuaDenHub), 0).toLocaleString()}
                    </td>
                    <td style={{ textAlign: 'right', color: '#ffffff' }}>
                      {incomingVehicles.reduce((a, b) => a + b.tongDon, 0).toLocaleString()}
                    </td>
                    <td style={{ textAlign: 'center', color: '#ffffff' }}>-</td>
                  </tr>
                )}
                {incomingVehicles.map((v, idx) => (
                  <tr key={v.station}>
                     <td className="highlight-val">{idx + 1}</td>
                     <td className="highlight-val">{v.station}</td>
                     <td className="highlight-green" style={{ textAlign: 'right' }}>{v.chuaDenHub.toLocaleString()}</td>
                     <td className="highlight-purple" style={{ textAlign: 'right' }}>{(v.tongDon - v.chuaDenHub).toLocaleString()}</td>
                     <td style={{ textAlign: 'right' }}>{v.tongDon.toLocaleString()}</td>
                     <td style={{ textAlign: 'center' }}>{v.lastTime ? v.lastTime.split(' ')[1] : '--:--'}</td>
                  </tr>
                ))}
                {incomingVehicles.length === 0 && (
                  <tr>
                    <td colSpan={6} style={{ textAlign: 'center', color: '#5a6578', padding: '20px' }}>Không có xe đang di chuyển</td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </div>
      </section>

      {/* Sync Button Row for Mobile/Desktop */}
      <div className="flex justify-end pt-4 gap-3">
        <button
          className="google-sync-btn"
          onClick={fetchAndUpdateData}
          disabled={loading}
          style={{ width: 'auto', padding: '10px 24px' }}
        >
          <span className="w-1.5 h-1.5 rounded-full bg-[#22c55e] animate-pulse shrink-0" style={{ marginRight: '8px' }} />
          {loading ? 'Đang đồng bộ...' : 'Đồng bộ'}
        </button>
      </div>
    </div>
  );
}
