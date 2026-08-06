import { useState, useMemo } from 'react';
import staticHeatmapData from '../data/heatmap.json';
import { Layers, Sparkles, Package, Truck, Inbox, ExternalLink, Calendar } from 'lucide-react';

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

interface WeekOption {
  weekNum: number;
  label: string;
  startDate: string;
  endDate: string;
}

// Generate 54 ISO Weeks for 2026 with explicit date range labels
const GENERATE_WEEKS_2026 = (): WeekOption[] => {
  const weeks: WeekOption[] = [];
  const startJan1 = new Date(2026, 0, 1);
  const dayOfWeek = startJan1.getDay(); // 4 (Thu)
  // Monday of W1 (Dec 29, 2025)
  const startW1 = new Date(2026, 0, 1 - ((dayOfWeek + 6) % 7));

  for (let w = 1; w <= 54; w++) {
    const wStart = new Date(startW1.getTime() + (w - 1) * 7 * 86400000);
    const wEnd = new Date(wStart.getTime() + 6 * 86400000);
    
    const formatDate = (dt: Date) => {
      const yyyy = dt.getFullYear();
      const mm = String(dt.getMonth() + 1).padStart(2, '0');
      const dd = String(dt.getDate()).padStart(2, '0');
      return `${yyyy}-${mm}-${dd}`;
    };

    const formatShort = (dt: Date) => {
      const mm = String(dt.getMonth() + 1).padStart(2, '0');
      const dd = String(dt.getDate()).padStart(2, '0');
      return `${dd}/${mm}`;
    };

    weeks.push({
      weekNum: w,
      label: `W${w} (${formatShort(wStart)} - ${formatShort(wEnd)})`,
      startDate: formatDate(wStart),
      endDate: formatDate(wEnd)
    });
  }
  return weeks;
};

const ALL_WEEKS = GENERATE_WEEKS_2026();

const DAYS_OF_WEEK = [
  { key: 'Mon', label: 'Thứ 2', code: 'Mon', dayIdx: 0 },
  { key: 'Tue', label: 'Thứ 3', code: 'Tue', dayIdx: 1 },
  { key: 'Wed', label: 'Thứ 4', code: 'Wed', dayIdx: 2 },
  { key: 'Thu', label: 'Thứ 5', code: 'Thu', dayIdx: 3 },
  { key: 'Fri', label: 'Thứ 6', code: 'Fri', dayIdx: 4 },
  { key: 'Sat', label: 'Thứ 7', code: 'Sat', dayIdx: 5 },
  { key: 'Sun', label: 'Chủ nhật', code: 'Sun', dayIdx: 6 }
];

const HOURS = [
  '06:00', '07:00', '08:00', '09:00', '10:00', '11:00', '12:00', '13:00', '14:00', '15:00', '16:00', '17:00',
  '18:00', '19:00', '20:00', '21:00', '22:00', '23:00', '00:00', '01:00', '02:00', '03:00', '04:00', '05:00'
];

export default function HeatmapDashboard({ loading, fetchAndUpdateData, lastUpdate, heatmapData: dynamicHeatmapData }: HeatmapDashboardProps) {
  const heatmapData = useMemo(() => {
    return Array.isArray(dynamicHeatmapData) && dynamicHeatmapData.length > 0 
      ? dynamicHeatmapData 
      : (Array.isArray(staticHeatmapData) ? staticHeatmapData : []);
  }, [dynamicHeatmapData]);

  // Default week: W32 (03/08 - 09/08/2026)
  const [selectedWeekNum, setSelectedWeekNum] = useState<number>(32);

  const currentWeek = useMemo(() => {
    return ALL_WEEKS.find(w => w.weekNum === selectedWeekNum) || ALL_WEEKS[31];
  }, [selectedWeekNum]);

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

  const isAllSelected = selectedStatuses.length === allOptions.length;

  const handleToggleAll = () => {
    if (isAllSelected) {
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

  // Map dates in the selected week to day of week
  const weekDatesMap = useMemo(() => {
    const map: Record<string, string> = {}; // dayKey (Mon..Sun) -> YYYY-MM-DD
    const wStart = new Date(currentWeek.startDate);
    DAYS_OF_WEEK.forEach((d, idx) => {
      const dt = new Date(wStart.getTime() + idx * 86400000);
      const yyyy = dt.getFullYear();
      const mm = String(dt.getMonth() + 1).padStart(2, '0');
      const dd = String(dt.getDate()).padStart(2, '0');
      map[d.key] = `${yyyy}-${mm}-${dd}`;
    });
    return map;
  }, [currentWeek]);

  // Index heatmap data by `${date}-${hour}` AND `${dayName}-${hour}` for fallback
  const cellMap = useMemo(() => {
    const map: Record<string, HeatCell> = {};
    heatmapData.forEach((d: any) => {
      if (d.date && d.hour !== undefined) {
        map[`${d.date}-${d.hour}`] = d;
      }
      if (d.dayName && d.hour !== undefined) {
        map[`${d.dayName}-${d.hour}`] = d;
      }
    });
    return map;
  }, [heatmapData]);

  // Get cell value dynamically based on selected checkboxes
  const getCellValue = (cell: HeatCell) => {
    let sum = 0;
    if (selectedStatuses.includes('created')) sum += cell.created || 0;
    if (selectedStatuses.includes('pickup')) sum += cell.pickup || 0;
    if (selectedStatuses.includes('transporting')) sum += cell.transporting || 0;
    if (selectedStatuses.includes('inbound')) sum += cell.inbound || 0;
    if (selectedStatuses.includes('outbound')) sum += cell.outbound || 0;
    return sum;
  };

  // Calculate maximum cell volume in current week view for normalisation
  const maxVal = useMemo(() => {
    let currentMax = 1;
    DAYS_OF_WEEK.forEach(d => {
      const dateStr = weekDatesMap[d.key];
      HOURS.forEach(hr => {
        const hourNum = parseInt(hr.split(':')[0], 10);
        const cell = cellMap[`${dateStr}-${hourNum}`] || cellMap[`${d.key}-${hourNum}`];
        if (cell) {
          const val = getCellValue(cell);
          if (val > currentMax) currentMax = val;
        }
      });
    });
    return currentMax;
  }, [cellMap, weekDatesMap, selectedStatuses]);

  // Design Color Palette Scale: #FF6115 (Large / Highest Volume) -> White / Neutral (Smallest / 0)
  const getCellColor = (cell: HeatCell) => {
    const val = getCellValue(cell);
    if (val === 0) return 'rgba(255, 255, 255, 0.04)';

    const ratio = Math.min(1, val / (maxVal || 1));
    // Color interpolation from White / Light Amber tint to #FF6115 (RGB: 255, 97, 21)
    const opacity = Math.max(0.15, Math.min(0.95, 0.2 + ratio * 0.75));
    const green = Math.round(255 - ratio * (255 - 97));   // 255 -> 97
    const blue = Math.round(255 - ratio * (255 - 21));    // 255 -> 21
    return `rgba(255, ${green}, ${blue}, ${opacity})`;
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
    <div className="w-full h-full overflow-y-auto px-4 pt-2 pb-12 font-sans select-none text-white animate-fade-in max-w-7xl mx-auto flex flex-col" style={{ gap: '12px' }}>
      {/* 1. Header Control Block */}
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

        {/* CENTER: Title */}
        <div className="text-center md:absolute md:left-1/2 md:-translate-x-1/2 pointer-events-none my-2 md:my-0 w-full md:w-auto">
          <h1 className="text-xl md:text-3xl lg:text-[36px] font-black tracking-tight leading-tight text-white" style={{ textShadow: '0 2px 20px rgba(255, 97, 21, 0.5)' }}>
            HCM HUB Operational Heatmap
          </h1>
          <p className="subtitle text-[10px] md:text-xs text-slate-400 mt-1">
            Weekly operational volume heatmap by Day of Week (Mon - Sun) & Operating Hour
          </p>
        </div>

        {/* RIGHT: Status Update */}
        <div className="header-right w-full md:w-auto flex justify-end md:block" style={{ flexShrink: 0 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
            <div style={{ 
              fontSize: '11px', 
              color: '#FF6115', 
              background: 'rgba(255, 97, 21, 0.08)', 
              border: '1px solid rgba(255, 97, 21, 0.3)', 
              padding: '5px 12px', 
              borderRadius: '20px', 
              fontWeight: 600, 
              fontFamily: "'Inter', sans-serif",
              display: 'flex',
              alignItems: 'center',
              gap: '6px',
              textShadow: '0 0 8px rgba(255, 97, 21, 0.4)'
            }}>
              <span className="w-1.5 h-1.5 rounded-full bg-[#FF6115] animate-pulse" />
              Update: {lastUpdate || 'Live System'}
            </div>
          </div>
        </div>
      </header>

      {/* 2. Control Bar: Isolated Week Picker (W1 -> W54) & Status Checkboxes */}
      <div className="jt-glowing-card p-4 flex flex-col lg:flex-row justify-between items-center gap-4" style={{ borderRadius: '12px' }}>
        
        {/* LEFT: Isolated Week Picker Dropdown (W1 -> W54) */}
        <div className="flex items-center gap-3 w-full lg:w-auto">
          <div className="w-9 h-9 rounded-full flex items-center justify-center bg-[#FF6115]/10 border border-[#FF6115]/40 shadow-[0_0_12px_rgba(255,97,21,0.3)] shrink-0">
            <Calendar size={16} className="text-[#FF6115] animate-pulse" />
          </div>
          <div className="flex flex-col">
            <span className="text-[10px] text-slate-400 font-extrabold uppercase tracking-wider">
              BỘ LỌC TUẦN (ISOLATED HEATMAP)
            </span>
            <div className="relative mt-1">
              <select
                value={selectedWeekNum}
                onChange={(e) => setSelectedWeekNum(Number(e.target.value))}
                className="bg-[#0f1117] text-white text-xs font-bold px-3 py-1.5 rounded-lg border border-[#FF6115]/40 focus:outline-none focus:border-[#FF6115] cursor-pointer shadow-[0_0_10px_rgba(255,97,21,0.15)] hover:border-[#FF6115]"
                style={{ appearance: 'auto' }}
              >
                {ALL_WEEKS.map((w) => (
                  <option key={w.weekNum} value={w.weekNum} className="bg-[#0f1117] text-white py-1">
                    {w.label} {w.weekNum === 32 ? '★ Tuần Hiện Tại' : ''}
                  </option>
                ))}
              </select>
            </div>
          </div>
        </div>

        {/* RIGHT: Inline Status Checkbox Toggles */}
        <div className="flex flex-wrap items-center gap-2 w-full lg:w-auto justify-start lg:justify-end">
          {/* Toggle All Option */}
          <div
            onClick={handleToggleAll}
            className={`flex items-center gap-2 px-3 py-1.5 rounded-lg border text-xs font-semibold cursor-pointer select-none transition-all ${
              isAllSelected 
                ? 'border-[#FF6115]/50 text-white shadow-[0_0_12px_rgba(255,97,21,0.3)]'
                : 'border-white/[0.04] text-slate-400 hover:text-slate-200 hover:border-white/20 hover:bg-white/[0.02]'
            }`}
            style={isAllSelected ? {
              background: 'linear-gradient(90deg, rgba(255, 97, 21, 0.85) 0%, rgba(225, 77, 10, 0.85) 100%)'
            } : {
              background: 'rgba(255, 255, 255, 0.02)'
            }}
          >
            <div className={`w-3.5 h-3.5 rounded border flex items-center justify-center transition-all ${
              isAllSelected ? 'border-amber-200 bg-amber-200 text-slate-900' : 'border-white/20 bg-black/30'
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
                    ? 'border-[#FF6115]/50 text-white shadow-[0_0_12px_rgba(255,97,21,0.3)]'
                    : 'border-white/[0.04] text-slate-400 hover:text-slate-200 hover:border-white/20 hover:bg-white/[0.02]'
                }`}
                style={isActive ? {
                  background: 'linear-gradient(90deg, rgba(255, 97, 21, 0.85) 0%, rgba(225, 77, 10, 0.85) 100%)'
                } : {
                  background: 'rgba(255, 255, 255, 0.02)'
                }}
              >
                <div className={`w-3.5 h-3.5 rounded border flex items-center justify-center transition-all ${
                  isActive ? 'border-amber-200 bg-amber-200 text-slate-900' : 'border-white/20 bg-black/30'
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

      {/* 3. Main Heatmap Grid: Y-Axis = Mon -> Sun (Thứ 2 -> Chủ Nhật), X-Axis = 24 Operating Hours */}
      <div className="jt-glowing-card p-6 relative">
        <div className="overflow-x-auto min-w-full scrollbar-thin">
          <div className="min-w-[960px] pb-4 relative">
            
            {/* Hours Header Row */}
            <div className="grid grid-cols-[100px_repeat(24,_1fr)] gap-1 sticky top-0 z-30 bg-[#16181e]/95 backdrop-blur-md py-3 mb-3 border-b border-white/[0.08]">
              <div className="text-xs text-slate-400 font-extrabold uppercase select-none flex items-center justify-end pr-3">
                Thứ \ Giờ
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

            {/* 7 Fixed Rows for Monday -> Sunday */}
            <div className="space-y-1.5">
              {DAYS_OF_WEEK.map((d) => {
                const dateStr = weekDatesMap[d.key];
                const dateParts = dateStr ? dateStr.split('-') : [];
                const formattedDateStr = dateParts.length === 3 ? `${dateParts[2]}/${dateParts[1]}` : '';

                return (
                  <div key={d.key} className="grid grid-cols-[100px_repeat(24,_1fr)] gap-1 items-center">
                    
                    {/* Y-Axis Label: Mon->Sun (Thứ 2 -> Chủ Nhật) */}
                    <div className="text-xs font-bold select-none text-right pr-3 h-9 flex flex-col justify-center items-end leading-tight">
                      <span className="text-[#FF6115] font-extrabold">{d.label}</span>
                      <span className="text-[10px] text-slate-400 font-mono">{formattedDateStr}</span>
                    </div>

                    {/* 24 Cells for Operating Hours (06:00 -> 05:00) */}
                    {HOURS.map((hr, hIdx) => {
                      const hourNum = parseInt(hr.split(':')[0], 10);
                      const cell = cellMap[`${dateStr}-${hourNum}`] || cellMap[`${d.key}-${hourNum}`] || {
                        date: dateStr,
                        dayName: d.key,
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
                          className="h-9 rounded-md transition-all duration-150 cursor-crosshair border border-white/[0.02] hover:scale-[1.12] hover:border-[#FF6115] hover:shadow-[0_0_14px_rgba(255,97,21,0.6)] relative z-10"
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
            
            {/* Color Palette Legend Bar (#FF6115 -> White) */}
            <div className="flex items-center justify-between mt-6 pt-4 border-t border-white/[0.06] text-xs text-slate-400">
              <div className="flex items-center gap-2">
                <span className="font-bold text-slate-300">Chuỗi Giờ Ca Vận Hành:</span>
                <span>06:00 sáng ➔ 05:00 sáng hôm sau</span>
              </div>
              <div className="flex items-center gap-3">
                <span className="text-[11px] font-bold text-slate-400">0 (Nhỏ)</span>
                <div className="w-32 h-3.5 rounded-full border border-white/10" style={{
                  background: 'linear-gradient(90deg, rgba(255, 255, 255, 0.1) 0%, rgba(255, 210, 185, 0.4) 40%, rgba(255, 97, 21, 0.95) 100%)'
                }} />
                <span className="text-[11px] font-extrabold text-[#FF6115]">Cao Nhất (#FF6115)</span>
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* Floating Tooltip Component */}
      {hoveredCell && (
        <div
          className="absolute z-50 pointer-events-none bg-[#090D16]/95 border border-[#FF6115]/40 rounded-xl p-3.5 shadow-[0_8px_32px_rgba(0,0,0,0.7)] backdrop-blur-md min-w-[230px]"
          style={{
            left: `${hoveredCell.x}px`,
            top: `${hoveredCell.y}px`,
            transform: 'translate(-50%, -100%)',
            transition: 'left 0.1s ease-out, top 0.1s ease-out'
          }}
        >
          {/* Tooltip Title */}
          <div className="text-[11px] text-[#FF6115] font-extrabold uppercase tracking-wider mb-2 border-b border-white/[0.08] pb-1.5 flex justify-between items-center">
            <span>{DAYS_OF_WEEK.find(d => d.key === hoveredCell.dayName)?.label || hoveredCell.dayName}</span>
            <span>{hoveredCell.date ? `${hoveredCell.date.split('-')[2]}/${hoveredCell.date.split('-')[1]}` : ''} - {String(hoveredCell.hour).padStart(2, '0')}:00</span>
          </div>
          
          {/* Tooltip Active Status Breakdown */}
          <div className="space-y-1">
            {selectedStatuses.includes('created') && (
              <div className="flex justify-between items-center py-0.5">
                <span className="text-[11px] text-slate-400 font-bold">Created:</span>
                <span className="text-[11px] text-slate-200 font-extrabold font-mono">{(hoveredCell.created || 0).toLocaleString()} đơn</span>
              </div>
            )}
            {selectedStatuses.includes('pickup') && (
              <div className="flex justify-between items-center py-0.5">
                <span className="text-[11px] text-slate-400 font-bold">Pickup Done:</span>
                <span className="text-[11px] text-slate-200 font-extrabold font-mono">{(hoveredCell.pickup || 0).toLocaleString()} đơn</span>
              </div>
            )}
            {selectedStatuses.includes('transporting') && (
              <div className="flex justify-between items-center py-0.5">
                <span className="text-[11px] text-slate-400 font-bold">Transporting:</span>
                <span className="text-[11px] text-slate-200 font-extrabold font-mono">{(hoveredCell.transporting || 0).toLocaleString()} đơn</span>
              </div>
            )}
            {selectedStatuses.includes('inbound') && (
              <div className="flex justify-between items-center py-0.5">
                <span className="text-[11px] text-slate-400 font-bold">Inbound:</span>
                <span className="text-[11px] text-slate-200 font-extrabold font-mono">{(hoveredCell.inbound || 0).toLocaleString()} đơn</span>
              </div>
            )}
            {selectedStatuses.includes('outbound') && (
              <div className="flex justify-between items-center py-0.5">
                <span className="text-[11px] text-slate-400 font-bold">Outbound:</span>
                <span className="text-[11px] text-slate-200 font-extrabold font-mono">{(hoveredCell.outbound || 0).toLocaleString()} đơn</span>
              </div>
            )}
            
            {/* Total Sum of Checked Statuses */}
            <div className="border-t border-white/[0.08] pt-1.5 mt-1.5 flex justify-between items-center font-bold">
              <span className="text-[11px] text-slate-200">Tổng Sản Lượng Trọng Yếu:</span>
              <span className="text-[12px] text-[#FF6115] font-extrabold font-mono">
                {Math.round(
                  (selectedStatuses.includes('created') ? (hoveredCell.created || 0) : 0) +
                  (selectedStatuses.includes('pickup') ? (hoveredCell.pickup || 0) : 0) +
                  (selectedStatuses.includes('transporting') ? (hoveredCell.transporting || 0) : 0) +
                  (selectedStatuses.includes('inbound') ? (hoveredCell.inbound || 0) : 0) +
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
