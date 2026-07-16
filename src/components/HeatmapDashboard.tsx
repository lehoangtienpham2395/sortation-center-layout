import { useState, useMemo } from 'react';
import heatmapData from '../data/heatmap.json';
import { Filter, Info } from 'lucide-react';

interface HeatCell {
  day: number;
  hour: number;
  created: number;
  pickup: number;
  transporting: number;
  inbound: number;
}

export default function HeatmapDashboard() {
  const [statusFilter, setStatusFilter] = useState<'all' | 'created' | 'pickup' | 'transporting' | 'inbound'>('all');
  const [hoveredCell, setHoveredCell] = useState<{
    day: number;
    hour: number;
    created: number;
    pickup: number;
    transporting: number;
    inbound: number;
    x: number;
    y: number;
  } | null>(null);

  const DAYS = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'];
  const DAYS_FULL = ['Thứ 2', 'Thứ 3', 'Thứ 4', 'Thứ 5', 'Thứ 6', 'Thứ 7', 'Chủ nhật'];
  const HOURS = [
    '06:00', '07:00', '08:00', '09:00', '10:00', '11:00', '12:00', '13:00', '14:00', '15:00', '16:00', '17:00',
    '18:00', '19:00', '20:00', '21:00', '22:00', '23:00', '00:00', '01:00', '02:00', '03:00', '04:00', '05:00'
  ];

  // Max values for normalization
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
    
    // For 'all', sum all stages
    const sum = cell.created + cell.pickup + cell.transporting + cell.inbound;
    return { val: sum, max: maxAll };
  };

  const getCellColor = (cell: HeatCell, filter: typeof statusFilter) => {
    const { val, max } = getCellValueAndMax(cell, filter);
    if (val === 0) return 'rgba(255, 255, 255, 0.02)';
    
    // Scale opacity between 0.08 and 0.95
    const ratio = val / max;
    const finalOpacity = Math.max(0.08, Math.min(0.95, ratio));

    // Lấy 1 màu chủ đạo làm chủ đạo (Emerald Green matching J&T accent #10b981)
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
    <div className="w-full h-full overflow-y-auto space-y-6 px-1 pt-2 pb-12 font-sans select-none text-white animate-fade-in">
      {/* Header card with glassmorphism */}
      <div className="table-container-card glass-card p-6 flex flex-col md:flex-row justify-between items-start md:items-center gap-4">
        <div>
          <h1 className="text-xl font-bold tracking-wider text-slate-100 flex items-center gap-2">
            BIỂU ĐỒ NHIỆT: HOẠT ĐỘNG THEO THỜI GIAN VÀ TRẠNG THÁI
          </h1>
          <p className="text-xs text-slate-400 mt-1">Phân tích lưu lượng truy cập hàng tuần</p>
        </div>

        {/* Filter Dropdown */}
        <div className="flex flex-col gap-1.5 self-stretch md:self-auto min-w-[240px]">
          <span className="text-[10px] text-slate-500 font-bold tracking-wider uppercase flex items-center gap-1.5">
            <Filter size={11} /> Bộ lọc chọn trạng thái hiển thị
          </span>
          <div className="relative">
            <select
              value={statusFilter}
              onChange={(e) => setStatusFilter(e.target.value as any)}
              className="w-full appearance-none bg-slate-900/60 border border-white/[0.08] hover:border-white/20 text-slate-200 text-xs px-3 py-2 pr-10 rounded-xl focus:outline-none cursor-pointer transition-colors shadow-lg"
            >
              <option value="all">Tất cả trạng thái</option>
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

      {/* Main Heatmap block */}
      <div className="table-container-card glass-card p-6 overflow-x-auto relative">
        {/* Legends Row */}
        <div className="flex flex-wrap justify-between items-center gap-4 mb-6 border-b border-white/[0.06] pb-4">
          <div className="flex items-center gap-2 text-xs text-slate-400">
            <Info size={14} className="text-emerald-400" />
            <span>Di chuột vào từng ô để xem chi tiết sản lượng bình quân theo giờ</span>
          </div>

          <div className="flex items-center gap-6 text-xs">
            {/* Color Gradient Legend */}
            <div className="flex items-center gap-2">
              <span className="text-slate-500">Màu nhạt (Low)</span>
              <div 
                className="w-24 h-2.5 rounded-full"
                style={{
                  background: 'linear-gradient(90deg, rgba(16, 185, 129, 0.08), rgba(16, 185, 129, 0.95))'
                }}
              />
              <span className="text-slate-300 font-bold">Màu đậm (High)</span>
            </div>

            {/* Stage legend info */}
            <div className="flex items-center gap-2.5">
              <div className="w-2 h-2 rounded bg-emerald-500" />
              <span className="text-slate-400 text-[11px] font-bold">Chủ đạo: Emerald Green</span>
            </div>
          </div>
        </div>

        {/* Heatmap Grid Wrapper */}
        <div className="min-w-[960px] pb-4">
          {/* Grid Rows for Days */}
          <div className="space-y-1">
            {DAYS.map((day, dIdx) => (
              <div key={day} className="grid grid-cols-[80px_repeat(24,_1fr)] gap-1 items-center">
                {/* Y Axis Label */}
                <div className="text-[11px] text-slate-400 font-bold select-none text-right pr-3 h-8 flex items-center justify-end">
                  {day}
                </div>

                {/* 24 Cells */}
                {HOURS.map((hr, hIdx) => {
                  const hourNum = parseInt(hr.split(':')[0], 10);
                  const cell = heatmapData.find(
                    (item: any) => item.day === dIdx && item.hour === hourNum
                  ) || { day: dIdx, hour: hourNum, created: 0, pickup: 0, transporting: 0, inbound: 0 };

                  const color = getCellColor(cell as any, statusFilter);

                  return (
                    <div
                      key={hIdx}
                      onMouseEnter={(e) => handleMouseEnter(cell as any, e)}
                      onMouseLeave={() => setHoveredCell(null)}
                      className="h-8 rounded-md transition-all duration-150 cursor-crosshair border border-white/[0.01] hover:scale-[1.08] hover:border-white/20 hover:shadow-[0_0_8px_rgba(16,185,129,0.35)] relative"
                      style={{
                        backgroundColor: color,
                      }}
                    />
                  );
                })}
              </div>
            ))}
          </div>

          {/* Hours Header Row - MOVED TO THE BOTTOM & FONT SIZE INCREASED */}
          <div className="grid grid-cols-[80px_repeat(24,_1fr)] gap-1 mt-4 pt-2 border-t border-white/[0.04]">
            <div className="text-xs text-slate-500 font-extrabold uppercase select-none flex items-center justify-end pr-3">
              Giờ
            </div>
            {HOURS.map((hr, idx) => (
              <div 
                key={idx}
                className="text-xs font-bold text-slate-300 text-center select-none py-1 hover:text-white transition-colors"
              >
                {hr.split(':')[0]}
              </div>
            ))}
          </div>
          
          {/* Bottom Hour-Axis title */}
          <div className="text-center text-xs text-slate-500 font-bold mt-3 tracking-wider uppercase">
            Chuỗi giờ ca vận hành (06:00 - 05:00)
          </div>
        </div>
      </div>

      {/* Floating Tooltip Component */}
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
          <div className="text-[10px] text-emerald-400 font-bold uppercase tracking-wider mb-1">
            {DAYS_FULL[hoveredCell.day]}, {String(hoveredCell.hour).padStart(2, '0')}:00
          </div>
          
          <div className="space-y-1 text-xs">
            <div className="flex justify-between gap-4">
              <span className="text-slate-400">Created (Dự báo):</span>
              <span className="font-semibold text-slate-200">{hoveredCell.created} đơn/h</span>
            </div>
            <div className="flex justify-between gap-4">
              <span className="text-slate-400">Pickup Done (Đã lấy):</span>
              <span className="font-semibold text-slate-200">{hoveredCell.pickup} đơn/h</span>
            </div>
            <div className="flex justify-between gap-4">
              <span className="text-slate-400">Transporting (Trung chuyển):</span>
              <span className="font-semibold text-slate-200">{hoveredCell.transporting} đơn/h</span>
            </div>
            <div className="flex justify-between gap-4">
              <span className="text-slate-400">Inbound (Nhập kho):</span>
              <span className="font-semibold text-emerald-400 font-bold">{hoveredCell.inbound} đơn/h</span>
            </div>
            <div className="border-t border-white/[0.06] pt-1 mt-1 flex justify-between gap-4 font-bold">
              <span className="text-slate-200">Tổng sản lượng:</span>
              <span className="text-emerald-400 text-[13px]">
                {Math.round(hoveredCell.created + hoveredCell.pickup + hoveredCell.transporting + hoveredCell.inbound)} đơn/h
              </span>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
