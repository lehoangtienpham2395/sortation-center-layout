import { useState, useMemo } from 'react';
import heatmapData from '../data/heatmap.json';
import { Filter, Info } from 'lucide-react';

interface HeatCell {
  date: string;
  dayName: string;
  hour: number;
  created: number;
  pickup: number;
  transporting: number;
  inbound: number;
}

interface HeatmapDashboardProps {
  loading?: boolean;
  fetchAndUpdateData?: () => void;
  lastUpdate?: string;
}

export default function HeatmapDashboard({ loading, fetchAndUpdateData, lastUpdate }: HeatmapDashboardProps) {
  const [statusFilter, setStatusFilter] = useState<'all' | 'created' | 'pickup' | 'transporting' | 'inbound'>('all');
  const [hoveredCell, setHoveredCell] = useState<{
    date: string;
    dayName: string;
    hour: number;
    created: number;
    pickup: number;
    transporting: number;
    inbound: number;
    x: number;
    y: number;
  } | null>(null);

  const HOURS = [
    '06:00', '07:00', '08:00', '09:00', '10:00', '11:00', '12:00', '13:00', '14:00', '15:00', '16:00', '17:00',
    '18:00', '19:00', '20:00', '21:00', '22:00', '23:00', '00:00', '01:00', '02:00', '03:00', '04:00', '05:00'
  ];

  const MAP_DAY_VN: Record<string, string> = {
    Mon: 'Thứ 2',
    Tue: 'Thứ 3',
    Wed: 'Thứ 4',
    Thu: 'Thứ 5',
    Fri: 'Thứ 6',
    Sat: 'Thứ 7',
    Sun: 'Chủ nhật'
  };

  // 1. Get unique operating dates in descending order (newest first)
  const uniqueDates = useMemo(() => {
    const dates = new Set<string>();
    heatmapData.forEach((d: any) => {
      if (d.date) dates.add(d.date);
    });
    return Array.from(dates);
  }, []);

  // 2. Map date to day name
  const dateToDayName = useMemo(() => {
    const mapping: Record<string, string> = {};
    heatmapData.forEach((d: any) => {
      if (d.date) mapping[d.date] = d.dayName;
    });
    return mapping;
  }, []);

  // 3. Helper to format date Y-axis label: "12/07-Sun"
  const formatDateLabel = (dateStr: string) => {
    const parts = dateStr.split('-');
    if (parts.length < 3) return dateStr;
    const dayName = dateToDayName[dateStr] || '';
    return `${parts[2]}/${parts[1]}-${dayName}`;
  };

  // 4. Pre-index heatmap data for O(1) cell lookup
  const cellMap = useMemo(() => {
    const map: Record<string, HeatCell> = {};
    heatmapData.forEach((d: any) => {
      map[`${d.date}-${d.hour}`] = d;
    });
    return map;
  }, []);

  // Max values for normalization based on actual daily values
  const maxCreated = useMemo(() => Math.max(...heatmapData.map((d: any) => d.created), 1), []);
  const maxPickup = useMemo(() => Math.max(...heatmapData.map((d: any) => d.pickup), 1), []);
  const maxTransporting = useMemo(() => Math.max(...heatmapData.map((d: any) => d.transporting), 1), []);
  const maxInbound = useMemo(() => Math.max(...heatmapData.map((d: any) => d.inbound), 1), []);
  const maxAll = useMemo(() => {
    const sums = heatmapData.map((d: any) => d.created + d.pickup + d.transporting + d.inbound);
    return Math.max(...sums, 1);
  }, []);

  const getCellValueAndMax = (cell: HeatCell, filter: typeof statusFilter) => {
    if (filter === 'created') return { val: cell.created, max: maxCreated };
    if (filter === 'pickup') return { val: cell.pickup, max: maxPickup };
    if (filter === 'transporting') return { val: cell.transporting, max: maxTransporting };
    if (filter === 'inbound') return { val: cell.inbound, max: maxInbound };
    
    const sum = cell.created + cell.pickup + cell.transporting + cell.inbound;
    return { val: sum, max: maxAll };
  };

  const getCellColor = (cell: HeatCell, filter: typeof statusFilter) => {
    const { val, max } = getCellValueAndMax(cell, filter);
    if (val === 0) return 'rgba(255, 255, 255, 0.02)';
    
    // Scale opacity between 0.08 and 0.95
    const ratio = val / max;
    const finalOpacity = Math.max(0.08, Math.min(0.95, ratio));

    // Lấy 1 màu chủ đạo (Emerald Green matching J&T accent #10b981)
    return `rgba(16, 185, 129, ${finalOpacity})`;
  };

  const handleMouseEnter = (cell: HeatCell, e: React.MouseEvent<HTMLDivElement>) => {
    const rect = e.currentTarget.getBoundingClientRect();
    setHoveredCell({
      ...cell,
      x: rect.left + window.scrollX + rect.width / 2,
      y: rect.top + window.scrollY - 10
    });
  };

  return (
    <div className="w-full h-full overflow-y-auto space-y-6 px-4 pt-2 pb-12 font-sans select-none text-white animate-fade-in max-w-7xl mx-auto">
      {/* 1. Header Control Block - Aligned with Inbound Dashboard style */}
      <header className="dashboard-header" style={{ position: 'relative', display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '14px 24px', minHeight: '100px' }}>
        
        {/* LEFT: Sync Button + Logo */}
        <div style={{ display: 'flex', alignItems: 'center', gap: '14px', flexShrink: 0 }}>
          {fetchAndUpdateData && (
            <button
              className="google-sync-btn"
              onClick={fetchAndUpdateData}
              disabled={loading}
              style={{ width: 'auto', padding: '10px 20px' }}
            >
              <span className="w-1.5 h-1.5 rounded-full bg-[#22c55e] animate-pulse shrink-0" style={{ marginRight: '8px' }} />
              {loading ? 'Đang đồng bộ...' : 'Đồng bộ'}
            </button>
          )}
          <img src="logo.png" alt="J&T Cargo Logo" className="jt-logo" style={{ height: '80px', borderRadius: '10px', display: 'block' }} />
        </div>

        {/* CENTER: Title — absolute center of header */}
        <div style={{ position: 'absolute', left: '50%', transform: 'translateX(-50%)', textAlign: 'center', pointerEvents: 'none' }}>
          <h1 style={{ fontSize: '36px', fontWeight: 900, color: '#fff', letterSpacing: '-0.5px', lineHeight: '1.1', textShadow: '0 2px 20px rgba(16, 185, 129, 0.5)', margin: 0, whiteSpace: 'nowrap' }}>
            HCM HUB Status Heatmap
          </h1>
          <p className="subtitle text-xs text-slate-400" style={{ marginTop: '4px', textAlign: 'center', display: 'block' }}>
            Hourly operational volume heatmap by operating date
          </p>
        </div>

        {/* RIGHT: Status Update */}
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
        </div>
      </header>

      {/* 2. Filter Bar - Styled like Layout Master control panels */}
      <div className="jt-glowing-card p-4 flex flex-col md:flex-row justify-between items-center gap-4 mt-6">
        <div className="flex items-center gap-2.5 text-xs text-slate-400">
          <Info size={14} className="text-emerald-400" />
          <span>Di chuột vào từng ô để xem chi tiết sản lượng của ngày đó theo trạng thái lọc</span>
        </div>

        {/* Filter Selector */}
        <div className="flex items-center gap-3">
          <span className="text-[10px] text-slate-400 font-bold tracking-wider uppercase flex items-center gap-1.5">
            <Filter size={11} /> Bộ lọc hiển thị:
          </span>
          <div className="relative min-w-[200px]">
            <select
              value={statusFilter}
              onChange={(e) => setStatusFilter(e.target.value as any)}
              className="w-full appearance-none bg-slate-900/60 border border-white/[0.08] hover:border-white/20 text-slate-200 text-xs px-3 py-2 pr-10 rounded-xl focus:outline-none cursor-pointer transition-colors shadow-lg"
            >
              <option value="all">Tất cả trạng thái (Total)</option>
              <option value="created">Created (Dự báo)</option>
              <option value="pickup">Pickup Done (Đã lấy hàng)</option>
              <option value="transporting">Transporting (Đang trung chuyển)</option>
              <option value="inbound">Inbound (Nhập kho)</option>
            </select>
            <div className="absolute inset-y-0 right-3 flex items-center pointer-events-none text-slate-400">
              <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" strokeWidth="2" viewBox="0 0 24 24">
                <path d="M19 9l-7 7-7-7" />
              </svg>
            </div>
          </div>
        </div>
      </div>

      {/* 3. Main Heatmap block - Styled like Layout Master tables inside jt-glowing-card */}
      <div className="jt-glowing-card p-6 overflow-x-auto relative">
        {/* Legends Row */}
        <div className="flex flex-wrap justify-between items-center gap-4 mb-6 border-b border-white/[0.06] pb-4">
          <div className="flex items-center gap-6 text-xs">
            {/* Color Gradient Legend */}
            <div className="flex items-center gap-2">
              <span className="text-slate-500">Màu nhạt (Thấp)</span>
              <div 
                className="w-24 h-2.5 rounded-full"
                style={{
                  background: 'linear-gradient(90deg, rgba(16, 185, 129, 0.08), rgba(16, 185, 129, 0.95))'
                }}
              />
              <span className="text-slate-300 font-bold">Màu đậm (Cao)</span>
            </div>

            <div className="flex items-center gap-2.5">
              <div className="w-2 h-2 rounded bg-emerald-500 shadow-[0_0_8px_#10b981]" />
              <span className="text-slate-400 text-[11px] font-bold">Chủ đạo: Emerald Green</span>
            </div>
          </div>
        </div>

        {/* Heatmap Grid Wrapper */}
        <div className="min-w-[960px] pb-4 relative">
          {/* Hours Header Row - STICKY AT THE TOP with premium background matching card */}
          <div className="grid grid-cols-[80px_repeat(24,_1fr)] gap-1 sticky top-0 z-30 bg-[#16181e]/95 backdrop-blur-md py-3 mb-3 border-b border-white/[0.06]">
            <div className="text-xs text-slate-500 font-extrabold uppercase select-none flex items-center justify-end pr-3">
              Giờ
            </div>
            {HOURS.map((hr, idx) => (
              <div 
                key={idx}
                className="text-xs font-bold text-slate-300 text-center select-none hover:text-white transition-colors"
              >
                {hr.split(':')[0]}
              </div>
            ))}
          </div>

          {/* Grid Rows for Days (Newest first) */}
          <div className="space-y-1">
            {uniqueDates.map((dateStr) => {
              const formattedLabel = formatDateLabel(dateStr);
              return (
                <div key={dateStr} className="grid grid-cols-[80px_repeat(24,_1fr)] gap-1 items-center">
                  {/* Y Axis Label */}
                  <div className="text-[11px] text-slate-400 font-bold select-none text-right pr-3 h-8 flex items-center justify-end">
                    {formattedLabel}
                  </div>

                  {/* 24 Cells */}
                  {HOURS.map((hr, hIdx) => {
                    const hourNum = parseInt(hr.split(':')[0], 10);
                    const cell = cellMap[`${dateStr}-${hourNum}`] || {
                      date: dateStr,
                      dayName: dateToDayName[dateStr] || '',
                      hour: hourNum,
                      created: 0,
                      pickup: 0,
                      transporting: 0,
                      inbound: 0
                    };

                    const color = getCellColor(cell, statusFilter);

                    return (
                      <div
                        key={hIdx}
                        onMouseEnter={(e) => handleMouseEnter(cell, e)}
                        onMouseLeave={() => setHoveredCell(null)}
                        className="h-8 rounded-md transition-all duration-150 cursor-crosshair border border-white/[0.01] hover:scale-[1.08] hover:border-white/20 hover:shadow-[0_0_8px_rgba(16,185,129,0.45)] relative"
                        style={{
                          backgroundColor: color,
                        }}
                      />
                    );
                  })}
                </div>
              );
            })}
          </div>
          
          {/* Bottom Hour-Axis title */}
          <div className="text-center text-xs text-slate-500 font-bold mt-4 tracking-wider uppercase">
            Chuỗi giờ ca vận hành (06:00 - 05:00)
          </div>
        </div>
      </div>

      {/* Floating Tooltip Component - Dynamically synced with statusFilter */}
      {hoveredCell && (
        <div
          className="absolute z-50 pointer-events-none bg-[#090D16]/95 border border-emerald-500/20 rounded-xl p-3 shadow-[0_8px_32px_rgba(0,0,0,0.5)] backdrop-blur-md"
          style={{
            left: `${hoveredCell.x}px`,
            top: `${hoveredCell.y}px`,
            transform: 'translate(-50%, -100%)',
            transition: 'left 0.1s ease-out, top 0.1s ease-out'
          }}
        >
          {/* Tooltip Title */}
          <div className="text-[10px] text-emerald-400 font-bold uppercase tracking-wider mb-1.5">
            {MAP_DAY_VN[hoveredCell.dayName] || hoveredCell.dayName},{' '}
            {hoveredCell.date.split('-')[2]}/{hoveredCell.date.split('-')[1]}, {String(hoveredCell.hour).padStart(2, '0')}:00
          </div>
          
          {/* Tooltip Content - Dynamically shows only active filtered status */}
          <div className="text-xs">
            {statusFilter === 'all' && (
              <div className="flex justify-between gap-4 font-bold text-white">
                <span className="text-slate-300">Tổng sản lượng (Total):</span>
                <span className="text-emerald-400 text-[13px]">
                  {Math.round(hoveredCell.created + hoveredCell.pickup + hoveredCell.transporting + hoveredCell.inbound).toLocaleString()} đơn
                </span>
              </div>
            )}
            {statusFilter === 'created' && (
              <div className="flex justify-between gap-4 font-semibold text-white">
                <span className="text-slate-400">Created (Dự báo):</span>
                <span className="text-emerald-400">{hoveredCell.created.toLocaleString()} đơn</span>
              </div>
            )}
            {statusFilter === 'pickup' && (
              <div className="flex justify-between gap-4 font-semibold text-white">
                <span className="text-slate-400">Pickup Done (Đã lấy):</span>
                <span className="text-emerald-400">{hoveredCell.pickup.toLocaleString()} đơn</span>
              </div>
            )}
            {statusFilter === 'transporting' && (
              <div className="flex justify-between gap-4 font-semibold text-white">
                <span className="text-slate-400">Transporting (Trung chuyển):</span>
                <span className="text-emerald-400">{hoveredCell.transporting.toLocaleString()} đơn</span>
              </div>
            )}
            {statusFilter === 'inbound' && (
              <div className="flex justify-between gap-4 font-semibold text-white">
                <span className="text-slate-400">Inbound (Nhập kho):</span>
                <span className="text-emerald-400">{hoveredCell.inbound.toLocaleString()} đơn</span>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
