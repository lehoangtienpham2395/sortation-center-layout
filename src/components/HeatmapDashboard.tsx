import { useState, useMemo } from 'react';
import staticHeatmapData from '../data/heatmap.json';
import { Filter, Layers, Sparkles, Package, Truck, Inbox, ExternalLink } from 'lucide-react';

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
  heatmapData?: any[];
}

export default function HeatmapDashboard({ loading, fetchAndUpdateData, lastUpdate, heatmapData: dynamicHeatmapData }: HeatmapDashboardProps) {
  const heatmapData = useMemo(() => {
    return Array.isArray(dynamicHeatmapData) && dynamicHeatmapData.length > 0 ? dynamicHeatmapData : (Array.isArray(staticHeatmapData) ? staticHeatmapData : []);
  }, [dynamicHeatmapData]);
  // Checkbox state: active selected statuses
  const allOptions = ['created', 'pickup', 'transporting', 'inbound', 'outbound'];
  const [selectedStatuses, setSelectedStatuses] = useState<string[]>(allOptions);

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

  const isAllSelected = selectedStatuses.length === allOptions.length;

  const handleToggleAll = () => {
    if (isAllSelected) {
      // Clear all except created to avoid blank view
      setSelectedStatuses(['created']);
    } else {
      setSelectedStatuses(allOptions);
    }
  };

  const handleToggleStatus = (val: string) => {
    if (selectedStatuses.includes(val)) {
      if (selectedStatuses.length > 1) {
        setSelectedStatuses(selectedStatuses.filter(s => s !== val));
      }
    } else {
      setSelectedStatuses([...selectedStatuses, val]);
    }
  };

  const renderOptionIcon = (iconName: string, size = 14, className = "") => {
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

  // Calculate cell value dynamically based on checked checkboxes
  const getCellValue = (cell: HeatCell) => {
    let sum = 0;
    if (selectedStatuses.includes('created')) sum += cell.created;
    if (selectedStatuses.includes('pickup')) sum += cell.pickup;
    if (selectedStatuses.includes('transporting')) sum += cell.transporting;
    if (selectedStatuses.includes('inbound')) sum += cell.inbound;
    if (selectedStatuses.includes('outbound')) sum += cell.outbound || 0;
    return sum;
  };

  // Max value dynamically recalculated for normalization
  const maxVal = useMemo(() => {
    let currentMax = 1;
    heatmapData.forEach((d: any) => {
      let sum = 0;
      if (selectedStatuses.includes('created')) sum += d.created;
      if (selectedStatuses.includes('pickup')) sum += d.pickup;
      if (selectedStatuses.includes('transporting')) sum += d.transporting;
      if (selectedStatuses.includes('inbound')) sum += d.inbound;
      if (selectedStatuses.includes('outbound')) sum += d.outbound || 0;
      if (sum > currentMax) currentMax = sum;
    });
    return currentMax;
  }, [selectedStatuses]);

  const getCellColor = (cell: HeatCell) => {
    const val = getCellValue(cell);
    if (val === 0) return 'rgba(255, 255, 255, 0.02)';
    
    // Scale opacity between 0.08 and 0.95
    const ratio = val / maxVal;
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
      {/* 1. Header Control Block - Responsive layout matching Inbound Dashboard */}
      <header className="dashboard-header flex flex-col md:flex-row items-center justify-between gap-4 relative" style={{ padding: '14px 24px', minHeight: '100px' }}>
        
        {/* LEFT: Sync Button + Logo */}
        <div className="flex items-center gap-3.5 w-full md:w-auto justify-between md:justify-start">
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

        {/* CENTER: Title — absolute center of header on desktop, stacked on mobile */}
        <div className="text-center md:absolute md:left-1/2 md:-translate-x-1/2 pointer-events-none my-2 md:my-0 w-full md:w-auto">
          <h1 className="text-xl md:text-3xl lg:text-[36px] font-black tracking-tight leading-tight text-white" style={{ textShadow: '0 2px 20px rgba(16, 185, 129, 0.5)' }}>
            HCM HUB Status Heatmap
          </h1>
          <p className="subtitle text-[10px] md:text-xs text-slate-400 mt-1">
            Hourly operational volume heatmap by operating date
          </p>
        </div>

        {/* RIGHT: Status Update */}
        <div className="header-right w-full md:w-auto flex justify-end md:block" style={{ flexShrink: 0 }}>
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
              Update: {lastUpdate || '20:04:02 29/07/2026'}
            </div>
          </div>
        </div>
      </header>

      {/* 2. Filter Bar - Inline checkboxes styled with 12px border radius */}
      <div className="jt-glowing-card p-4 flex flex-col md:flex-row justify-between items-center gap-4" style={{ borderRadius: '12px' }}>
        {/* Left Side: Glowing Filter Icon + Title Status */}
        <div className="flex items-center gap-3">
          <div className="w-9 h-9 rounded-full flex items-center justify-center bg-teal-500/10 border border-teal-500/35 shadow-[0_0_10px_rgba(20,184,166,0.25)] shrink-0">
            <Filter size={16} className="text-teal-400 animate-pulse" />
          </div>
          <span className="text-[13px] text-slate-100 font-extrabold tracking-widest uppercase">
            STATUS
          </span>
        </div>

        {/* Right Side: Inline Checkbox Toggles (No Vietnamese) */}
        <div className="flex flex-wrap items-center gap-2">
          {/* Toggle All (Total) Option */}
          <div
            onClick={handleToggleAll}
            className={`flex items-center gap-2 px-3 py-1.5 rounded-lg border text-xs font-semibold cursor-pointer select-none transition-all ${
              isAllSelected 
                ? 'border-teal-500/30 text-white shadow-[0_0_10px_rgba(20,184,166,0.2)]'
                : 'border-white/[0.04] text-slate-400 hover:text-slate-200 hover:border-white/20 hover:bg-white/[0.02]'
            }`}
            style={isAllSelected ? {
              background: 'linear-gradient(90deg, rgba(20, 184, 166, 0.75) 0%, rgba(13, 148, 136, 0.75) 100%)'
            } : {
              background: 'rgba(255, 255, 255, 0.02)'
            }}
          >
            <div className={`w-3.5 h-3.5 rounded border flex items-center justify-center transition-all ${
              isAllSelected ? 'border-teal-300 bg-teal-300 text-slate-900' : 'border-white/20 bg-black/30'
            }`}>
              {isAllSelected && (
                <svg className="w-2.5 h-2.5 text-slate-900 stroke-[3.5]" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" d="M5 13l4 4L19 7" />
                </svg>
              )}
            </div>
            {renderOptionIcon('Layers', 13, isAllSelected ? "text-white" : "text-slate-400")}
            <span>Total</span>
          </div>

          {/* Individual Status Checkboxes */}
          {[
            { value: 'created', label: 'Created', icon: 'Sparkles' },
            { value: 'pickup', label: 'Pickup Done', icon: 'Package' },
            { value: 'transporting', label: 'Transporting', icon: 'Truck' },
            { value: 'inbound', label: 'Inbound', icon: 'Inbox' },
            { value: 'outbound', label: 'Outbound', icon: 'ExternalLink' }
          ].map((opt) => {
            const isActive = selectedStatuses.includes(opt.value);
            return (
              <div
                key={opt.value}
                onClick={() => handleToggleStatus(opt.value)}
                className={`flex items-center gap-2 px-3 py-1.5 rounded-lg border text-xs font-semibold cursor-pointer select-none transition-all ${
                  isActive 
                    ? 'border-teal-500/30 text-white shadow-[0_0_10px_rgba(20,184,166,0.2)]'
                    : 'border-white/[0.04] text-slate-400 hover:text-slate-200 hover:border-white/20 hover:bg-white/[0.02]'
                }`}
                style={isActive ? {
                  background: 'linear-gradient(90deg, rgba(20, 184, 166, 0.75) 0%, rgba(13, 148, 136, 0.75) 100%)'
                } : {
                  background: 'rgba(255, 255, 255, 0.02)'
                }}
              >
                <div className={`w-3.5 h-3.5 rounded border flex items-center justify-center transition-all ${
                  isActive ? 'border-teal-300 bg-teal-300 text-slate-900' : 'border-white/20 bg-black/30'
                }`}>
                  {isActive && (
                    <svg className="w-2.5 h-2.5 text-slate-900 stroke-[3.5]" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" d="M5 13l4 4L19 7" />
                    </svg>
                  )}
                </div>
                {renderOptionIcon(opt.icon, 13, isActive ? "text-white" : "text-slate-400")}
                <span>{opt.label}</span>
              </div>
            );
          })}
        </div>
      </div>

      {/* 3. Main Heatmap block - Styled like Layout Master tables inside jt-glowing-card */}
      <div className="jt-glowing-card p-6 relative">


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

                      const color = getCellColor(cell);

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

      {/* Floating Tooltip Component - Dynamically synced with selectedStatuses */}
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
          
          {/* Tooltip Content - Aligned key-value structure of selected active options */}
          <div className="space-y-1">
            {selectedStatuses.includes('created') && (
              <div className="flex justify-between items-center py-0.5">
                <span className="text-[11px] text-slate-400 font-bold">Created:</span>
                <span className="text-[11px] text-slate-200 font-extrabold font-mono">{hoveredCell.created.toLocaleString()} đơn</span>
              </div>
            )}
            {selectedStatuses.includes('pickup') && (
              <div className="flex justify-between items-center py-0.5">
                <span className="text-[11px] text-slate-400 font-bold">Pickup Done:</span>
                <span className="text-[11px] text-slate-200 font-extrabold font-mono">{hoveredCell.pickup.toLocaleString()} đơn</span>
              </div>
            )}
            {selectedStatuses.includes('transporting') && (
              <div className="flex justify-between items-center py-0.5">
                <span className="text-[11px] text-slate-400 font-bold">Transporting:</span>
                <span className="text-[11px] text-slate-200 font-extrabold font-mono">{hoveredCell.transporting.toLocaleString()} đơn</span>
              </div>
            )}
            {selectedStatuses.includes('inbound') && (
              <div className="flex justify-between items-center py-0.5">
                <span className="text-[11px] text-slate-400 font-bold">Inbound:</span>
                <span className="text-[11px] text-slate-200 font-extrabold font-mono">{hoveredCell.inbound.toLocaleString()} đơn</span>
              </div>
            )}
            {selectedStatuses.includes('outbound') && (
              <div className="flex justify-between items-center py-0.5">
                <span className="text-[11px] text-slate-400 font-bold">Outbound:</span>
                <span className="text-[11px] text-slate-200 font-extrabold font-mono">{(hoveredCell.outbound || 0).toLocaleString()} đơn</span>
              </div>
            )}
            
            {/* Divider and Total Sum of checked items */}
            <div className="border-t border-white/[0.08] pt-1.5 mt-1.5 flex justify-between items-center font-bold">
              <span className="text-[11px] text-slate-200">Total Selected:</span>
              <span className="text-[12px] text-emerald-400 font-extrabold font-mono">
                {Math.round(
                  (selectedStatuses.includes('created') ? hoveredCell.created : 0) +
                  (selectedStatuses.includes('pickup') ? hoveredCell.pickup : 0) +
                  (selectedStatuses.includes('transporting') ? hoveredCell.transporting : 0) +
                  (selectedStatuses.includes('inbound') ? hoveredCell.inbound : 0) +
                  (selectedStatuses.includes('outbound') ? (hoveredCell.outbound || 0) : 0)
                ).toLocaleString()} đơn
              </span>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
