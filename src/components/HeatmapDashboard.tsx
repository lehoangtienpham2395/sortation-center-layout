import { useState, useMemo } from 'react';
import heatmapData from '../data/heatmap.json';
import { Filter, Layers, Sparkles, Package, Truck, Inbox, ExternalLink, ChevronDown } from 'lucide-react';

interface HeatCell {
  date: string;
  dayName: string;
  hour: number;
  created: number;
  pickup: number;
  transporting: number;
  inbound: number;
  outbound: number;
}

interface HeatmapDashboardProps {
  loading?: boolean;
  fetchAndUpdateData?: () => void;
  lastUpdate?: string;
}

export default function HeatmapDashboard({ loading, fetchAndUpdateData, lastUpdate }: HeatmapDashboardProps) {
  const [statusFilter, setStatusFilter] = useState<'all' | 'created' | 'pickup' | 'transporting' | 'inbound' | 'outbound'>('all');
  const [dropdownOpen, setDropdownOpen] = useState(false);
  const [hoveredCell, setHoveredCell] = useState<{
    date: string;
    dayName: string;
    hour: number;
    created: number;
    pickup: number;
    transporting: number;
    inbound: number;
    outbound: number;
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

  const filterOptions = [
    { value: 'all', label: 'Tất cả trạng thái (Total)', icon: 'Layers' },
    { value: 'created', label: 'Created (Dự báo)', icon: 'Sparkles' },
    { value: 'pickup', label: 'Pickup Done (Đã lấy hàng)', icon: 'Package' },
    { value: 'transporting', label: 'Transporting (Đang trung chuyển)', icon: 'Truck' },
    { value: 'inbound', label: 'Inbound (Nhập kho)', icon: 'Inbox' },
    { value: 'outbound', label: 'Outbound (Xuất kho)', icon: 'ExternalLink' }
  ];

  const selectedOption = useMemo(() => {
    return filterOptions.find(opt => opt.value === statusFilter) || filterOptions[0];
  }, [statusFilter]);

  const renderOptionIcon = (iconName: string, size = 16, className = "") => {
    if (iconName === 'Layers') return <Layers size={size} className={className} />;
    if (iconName === 'Sparkles') return <Sparkles size={size} className={className} />;
    if (iconName === 'Package') return <Package size={size} className={className} />;
    if (iconName === 'Truck') return <Truck size={size} className={className} />;
    if (iconName === 'Inbox') return <Inbox size={size} className={className} />;
    if (iconName === 'ExternalLink') return <ExternalLink size={size} className={className} />;
    return null;
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
  const maxOutbound = useMemo(() => Math.max(...heatmapData.map((d: any) => d.outbound || 0), 1), []);
  const maxAll = useMemo(() => {
    const sums = heatmapData.map((d: any) => d.created + d.pickup + d.transporting + d.inbound + (d.outbound || 0));
    return Math.max(...sums, 1);
  }, []);

  const getCellValueAndMax = (cell: HeatCell, filter: typeof statusFilter) => {
    if (filter === 'created') return { val: cell.created, max: maxCreated };
    if (filter === 'pickup') return { val: cell.pickup, max: maxPickup };
    if (filter === 'transporting') return { val: cell.transporting, max: maxTransporting };
    if (filter === 'inbound') return { val: cell.inbound, max: maxInbound };
    if (filter === 'outbound') return { val: cell.outbound || 0, max: maxOutbound };
    
    const sum = cell.created + cell.pickup + cell.transporting + cell.inbound + (cell.outbound || 0);
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
    <div className="w-full h-full overflow-y-auto px-4 pt-2 pb-12 font-sans select-none text-white animate-fade-in max-w-7xl mx-auto flex flex-col" style={{ gap: '10px' }}>
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

      {/* 2. Filter Bar - High-tech glassmorphism style matching concept image */}
      <div className="jt-glowing-card p-4 flex justify-between items-center relative z-40">
        {/* Left Side: Glowing Filter Icon + Title */}
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-full flex items-center justify-center bg-teal-500/10 border border-teal-500/35 shadow-[0_0_12px_rgba(20,184,166,0.25)] shrink-0">
            <Filter size={18} className="text-teal-400 animate-pulse" />
          </div>
          <span className="text-[13px] text-slate-100 font-extrabold tracking-widest uppercase">
            THIẾT LẬP BỘ LỌC
          </span>
        </div>

        {/* Right Side: Custom Dropdown Trigger */}
        <div className="relative">
          <button
            onClick={() => setDropdownOpen(!dropdownOpen)}
            className="flex items-center justify-between gap-3 min-w-[260px] px-4 py-2.5 rounded-xl border border-white/10 text-white text-xs font-bold transition-all shadow-[0_4px_15px_rgba(0,0,0,0.3)] hover:scale-[1.02] cursor-pointer"
            style={{
              background: 'linear-gradient(90deg, rgba(20, 184, 166, 0.75) 0%, rgba(13, 148, 136, 0.75) 100%)',
              boxShadow: '0 0 15px rgba(20, 184, 166, 0.15)'
            }}
          >
            <div className="flex items-center gap-2.5">
              {renderOptionIcon(selectedOption.icon, 15, "text-white")}
              <span>{selectedOption.label}</span>
            </div>
            <ChevronDown size={14} className={`text-white/80 transition-transform ${dropdownOpen ? 'rotate-180' : ''}`} />
          </button>

          {/* Custom Dropdown List */}
          {dropdownOpen && (
            <div 
              className="absolute right-0 mt-2 min-w-[280px] bg-[#0c101c]/95 border border-white/10 rounded-xl p-1.5 shadow-[0_12px_40px_rgba(0,0,0,0.65)] backdrop-blur-xl z-50 space-y-1 animate-fade-in"
              style={{ boxShadow: '0 0 20px rgba(20, 184, 166, 0.08)' }}
            >
              {filterOptions.map((opt) => {
                const isActive = opt.value === statusFilter;
                return (
                  <button
                    key={opt.value}
                    onClick={() => {
                      setStatusFilter(opt.value as any);
                      setDropdownOpen(false);
                    }}
                    className={`w-full flex items-center gap-3 px-3 py-2 rounded-lg border text-left text-xs font-semibold transition-all cursor-pointer ${
                      isActive 
                        ? 'border-teal-500/30 text-white shadow-[0_0_12px_rgba(20,184,166,0.2)]'
                        : 'border-white/[0.04] text-slate-300 hover:text-white hover:border-teal-500/20 hover:bg-teal-500/[0.04] hover:shadow-[0_0_8px_rgba(20,184,166,0.1)]'
                    }`}
                    style={isActive ? {
                      background: 'linear-gradient(90deg, rgba(20, 184, 166, 0.8) 0%, rgba(13, 148, 136, 0.8) 100%)'
                    } : {
                      background: 'rgba(255, 255, 255, 0.02)'
                    }}
                  >
                    {renderOptionIcon(opt.icon, 14, isActive ? "text-white" : "text-slate-400")}
                    <span>{opt.label}</span>
                  </button>
                );
              })}
            </div>
          )}
        </div>
      </div>

      {/* 3. Main Heatmap block - Styled like Layout Master tables inside jt-glowing-card */}
      <div className="jt-glowing-card p-6 relative">
        {/* Legends Row */}
        <div className="flex flex-wrap justify-between items-center gap-4 mb-4 border-b border-white/[0.06] pb-4 flex-shrink-0">
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

        {/* Heatmap Grid Wrapper with horizontal scroll */}
        <div className="overflow-x-auto min-w-full scrollbar-thin">
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
                        inbound: 0,
                        outbound: 0
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
      </div>

      {/* Floating Tooltip Component - Dynamically synced with statusFilter */}
      {hoveredCell && (
        <div
          className="absolute z-50 pointer-events-none bg-[#090D16]/95 border border-emerald-500/20 rounded-xl p-3 shadow-[0_8px_32px_rgba(0,0,0,0.5)] backdrop-blur-md min-w-[220px]"
          style={{
            left: `${hoveredCell.x}px`,
            top: `${hoveredCell.y}px`,
            transform: 'translate(-50%, -100%)',
            transition: 'left 0.1s ease-out, top 0.1s ease-out'
          }}
        >
          {/* Tooltip Title */}
          <div className="text-[10px] text-emerald-400 font-extrabold uppercase tracking-wider mb-2 border-b border-white/[0.08] pb-1.5 flex justify-between items-center">
            <span>{MAP_DAY_VN[hoveredCell.dayName] || hoveredCell.dayName}</span>
            <span>{hoveredCell.date.split('-')[2]}/{hoveredCell.date.split('-')[1]} - {String(hoveredCell.hour).padStart(2, '0')}:00</span>
          </div>
          
          {/* Tooltip Content - Aligned key-value structure matching Master Layout panel */}
          <div className="space-y-1">
            {statusFilter === 'all' ? (
              <>
                <div className="flex justify-between items-center py-0.5">
                  <span className="text-[11px] text-slate-400 font-bold">Created (Dự báo):</span>
                  <span className="text-[11px] text-slate-200 font-extrabold font-mono">{hoveredCell.created.toLocaleString()} đơn</span>
                </div>
                <div className="flex justify-between items-center py-0.5">
                  <span className="text-[11px] text-slate-400 font-bold">Pickup Done (Đã lấy):</span>
                  <span className="text-[11px] text-slate-200 font-extrabold font-mono">{hoveredCell.pickup.toLocaleString()} đơn</span>
                </div>
                <div className="flex justify-between items-center py-0.5">
                  <span className="text-[11px] text-slate-400 font-bold">Transporting (Trung chuyển):</span>
                  <span className="text-[11px] text-slate-200 font-extrabold font-mono">{hoveredCell.transporting.toLocaleString()} đơn</span>
                </div>
                <div className="flex justify-between items-center py-0.5">
                  <span className="text-[11px] text-slate-400 font-bold">Inbound (Nhập kho):</span>
                  <span className="text-[11px] text-slate-200 font-extrabold font-mono">{hoveredCell.inbound.toLocaleString()} đơn</span>
                </div>
                <div className="flex justify-between items-center py-0.5">
                  <span className="text-[11px] text-slate-400 font-bold">Outbound (Xuất kho):</span>
                  <span className="text-[11px] text-slate-200 font-extrabold font-mono">{(hoveredCell.outbound || 0).toLocaleString()} đơn</span>
                </div>
                <div className="border-t border-white/[0.08] pt-1.5 mt-1.5 flex justify-between items-center font-bold">
                  <span className="text-[11px] text-slate-200">Total (Tổng số):</span>
                  <span className="text-[12px] text-emerald-400 font-extrabold font-mono">
                    {Math.round(hoveredCell.created + hoveredCell.pickup + hoveredCell.transporting + hoveredCell.inbound + (hoveredCell.outbound || 0)).toLocaleString()} đơn
                  </span>
                </div>
              </>
            ) : (
              <>
                {statusFilter === 'created' && (
                  <div className="flex justify-between items-center py-0.5">
                    <span className="text-[11px] text-slate-400 font-bold">Created (Dự báo):</span>
                    <span className="text-[11px] text-emerald-400 font-extrabold font-mono">{hoveredCell.created.toLocaleString()} đơn</span>
                  </div>
                )}
                {statusFilter === 'pickup' && (
                  <div className="flex justify-between items-center py-0.5">
                    <span className="text-[11px] text-slate-400 font-bold">Pickup Done (Đã lấy):</span>
                    <span className="text-[11px] text-emerald-400 font-extrabold font-mono">{hoveredCell.pickup.toLocaleString()} đơn</span>
                  </div>
                )}
                {statusFilter === 'transporting' && (
                  <div className="flex justify-between items-center py-0.5">
                    <span className="text-[11px] text-slate-400 font-bold">Transporting (Trung chuyển):</span>
                    <span className="text-[11px] text-emerald-400 font-extrabold font-mono">{hoveredCell.transporting.toLocaleString()} đơn</span>
                  </div>
                )}
                {statusFilter === 'inbound' && (
                  <div className="flex justify-between items-center py-0.5">
                    <span className="text-[11px] text-slate-400 font-bold">Inbound (Nhập kho):</span>
                    <span className="text-[11px] text-emerald-400 font-extrabold font-mono">{hoveredCell.inbound.toLocaleString()} đơn</span>
                  </div>
                )}
                {statusFilter === 'outbound' && (
                  <div className="flex justify-between items-center py-0.5">
                    <span className="text-[11px] text-slate-400 font-bold">Outbound (Xuất kho):</span>
                    <span className="text-[11px] text-emerald-400 font-extrabold font-mono">{(hoveredCell.outbound || 0).toLocaleString()} đơn</span>
                  </div>
                )}
              </>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
