import { useState, useMemo } from 'react';
import heatmapData from '../data/heatmap.json';
import { Filter, Info } from 'lucide-react';

interface HeatCell {
  day: number;
  hour: number;
  active: number;
  pending: number;
  completed: number;
}

export default function HeatmapDashboard() {
  const [statusFilter, setStatusFilter] = useState<'all' | 'active' | 'pending' | 'completed'>('all');
  const [hoveredCell, setHoveredCell] = useState<{
    day: number;
    hour: number;
    active: number;
    pending: number;
    completed: number;
    x: number;
    y: number;
  } | null>(null);

  const DAYS = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'];
  const DAYS_FULL = ['Thứ 2', 'Thứ 3', 'Thứ 4', 'Thứ 5', 'Thứ 6', 'Thứ 7', 'Chủ nhật'];
  const HOURS = Array.from({ length: 24 }, (_, i) => `${String(i).padStart(2, '0')}:00`);

  // Max values for normalization
  const maxActive = useMemo(() => Math.max(...heatmapData.map((d: any) => d.active), 1), []);
  const maxPending = useMemo(() => Math.max(...heatmapData.map((d: any) => d.pending), 1), []);
  const maxCompleted = useMemo(() => Math.max(...heatmapData.map((d: any) => d.completed), 1), []);
  
  const getCellOpacity = (cell: HeatCell, filter: typeof statusFilter) => {
    if (filter === 'active') return cell.active / maxActive;
    if (filter === 'pending') return cell.pending / maxPending;
    if (filter === 'completed') return cell.completed / maxCompleted;
    
    // For 'all', find dominant status and return opacity based on that
    const maxVal = Math.max(cell.active, cell.pending, cell.completed);
    if (maxVal === 0) return 0;
    if (maxVal === cell.active) return cell.active / maxActive;
    if (maxVal === cell.pending) return cell.pending / maxPending;
    return cell.completed / maxCompleted;
  };

  const getCellColor = (cell: HeatCell, filter: typeof statusFilter, opacity: number) => {
    if (opacity === 0) return 'rgba(255, 255, 255, 0.02)';
    
    // Smooth minimum opacity for visibility
    const finalOpacity = Math.max(0.12, opacity);

    if (filter === 'active') {
      return `rgba(34, 197, 94, ${finalOpacity})`; // Green Emerald
    }
    if (filter === 'pending') {
      return `rgba(56, 189, 248, ${finalOpacity})`; // Blue Sky
    }
    if (filter === 'completed') {
      return `rgba(148, 163, 184, ${finalOpacity})`; // Grey Slate
    }

    // For 'all', color based on dominant status
    const maxVal = Math.max(cell.active, cell.pending, cell.completed);
    if (maxVal === cell.active) {
      return `rgba(34, 197, 94, ${finalOpacity})`;
    }
    if (maxVal === cell.pending) {
      return `rgba(56, 189, 248, ${finalOpacity})`;
    }
    return `rgba(148, 163, 184, ${finalOpacity})`;
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
    <div className="w-full h-full overflow-y-auto space-y-6 px-1 pt-2 pb-12 font-sans select-none text-white">
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
              <option value="active">Hoạt động</option>
              <option value="pending">Chờ</option>
              <option value="completed">Đã hoàn thành</option>
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
              <span className="text-slate-500">Low Activity</span>
              <div 
                className="w-24 h-2.5 rounded-full"
                style={{
                  background: statusFilter === 'active'
                    ? 'linear-gradient(90deg, rgba(34, 197, 94, 0.1), rgba(34, 197, 94, 1))'
                    : statusFilter === 'pending'
                    ? 'linear-gradient(90deg, rgba(56, 189, 248, 0.1), rgba(56, 189, 248, 1))'
                    : statusFilter === 'completed'
                    ? 'linear-gradient(90deg, rgba(148, 163, 184, 0.1), rgba(148, 163, 184, 1))'
                    : 'linear-gradient(90deg, rgba(34, 197, 94, 0.1), rgba(34, 197, 94, 1))'
                }}
              />
              <span className="text-slate-300">100 (Max)</span>
            </div>

            {/* Status indicators */}
            <div className="flex items-center gap-3">
              <div className="flex items-center gap-1.5">
                <div className="w-2.5 h-2.5 rounded bg-emerald-500" />
                <span className="text-slate-400">Active</span>
              </div>
              <div className="flex items-center gap-1.5">
                <div className="w-2.5 h-2.5 rounded bg-sky-400" />
                <span className="text-slate-400">Pending</span>
              </div>
              <div className="flex items-center gap-1.5">
                <div className="w-2.5 h-2.5 rounded bg-slate-400" />
                <span className="text-slate-400">Completed</span>
              </div>
            </div>
          </div>
        </div>

        {/* Heatmap Grid Wrapper */}
        <div className="min-w-[960px] pb-4">
          {/* Hours Header Row */}
          <div className="grid grid-cols-[80px_repeat(24,_1fr)] gap-1 mb-2">
            <div className="text-[10px] text-slate-500 font-bold uppercase select-none flex items-center justify-center">
              Thứ / Giờ
            </div>
            {HOURS.map((hr, idx) => (
              <div 
                key={idx}
                className="text-[9px] text-slate-400 font-medium text-center select-none py-1 hover:text-white transition-colors"
              >
                {hr.split(':')[0]}
              </div>
            ))}
          </div>

          {/* Grid Rows for Days */}
          <div className="space-y-1">
            {DAYS.map((day, dIdx) => (
              <div key={day} className="grid grid-cols-[80px_repeat(24,_1fr)] gap-1 items-center">
                {/* Y Axis Label */}
                <div className="text-[11px] text-slate-400 font-bold select-none text-right pr-3 h-8 flex items-center justify-end">
                  {day}
                </div>

                {/* 24 Cells */}
                {HOURS.map((_, hIdx) => {
                  const cell = heatmapData.find(
                    (item: any) => item.day === dIdx && item.hour === hIdx
                  ) || { day: dIdx, hour: hIdx, active: 0, pending: 0, completed: 0 };

                  const opacity = getCellOpacity(cell, statusFilter);
                  const color = getCellColor(cell, statusFilter, opacity);

                  return (
                    <div
                      key={hIdx}
                      onMouseEnter={(e) => handleMouseEnter(cell, e)}
                      onMouseLeave={() => setHoveredCell(null)}
                      className="h-8 rounded-md transition-all duration-150 cursor-crosshair border border-white/[0.01] hover:scale-[1.08] hover:border-white/20 hover:shadow-[0_0_8px_rgba(255,255,255,0.1)] relative"
                      style={{
                        backgroundColor: color,
                      }}
                    />
                  );
                })}
              </div>
            ))}
          </div>
          
          {/* Bottom Hour-Axis title */}
          <div className="text-center text-xs text-slate-500 font-bold mt-4 tracking-wider">
            Chuỗi giờ 0-23
          </div>
        </div>
      </div>

      {/* Floating Tooltip Component */}
      {hoveredCell && (
        <div
          className="absolute z-50 pointer-events-none bg-[#090D16]/95 border border-white/[0.08] rounded-xl p-3 shadow-[0_8px_32px_rgba(0,0,0,0.5)] backdrop-blur-md"
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
              <span className="text-slate-400">Hoạt động (Active):</span>
              <span className="font-semibold text-emerald-400">{hoveredCell.active} đơn/h</span>
            </div>
            <div className="flex justify-between gap-4">
              <span className="text-slate-400">Chờ (Pending):</span>
              <span className="font-semibold text-sky-400">{hoveredCell.pending} đơn/h</span>
            </div>
            <div className="flex justify-between gap-4">
              <span className="text-slate-400">Đã xong (Completed):</span>
              <span className="font-semibold text-slate-300">{hoveredCell.completed} đơn/h</span>
            </div>
            <div className="border-t border-white/[0.06] pt-1 mt-1 flex justify-between gap-4 font-bold">
              <span className="text-slate-200">Tổng sản lượng:</span>
              <span className="text-white">
                {Math.round(hoveredCell.active + hoveredCell.pending + hoveredCell.completed)} đơn/h
              </span>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
