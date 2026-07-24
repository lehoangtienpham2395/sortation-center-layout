import React, { useState, useEffect, useRef } from 'react';

export interface DatePickerProps {
  selectedDate: string; // "YYYY-MM-DD"
  onDateChange: (dateStr: string) => void;
  availableDates?: string[]; // Array of "YYYY-MM-DD"
  label?: string;
  className?: string;
  buttonClassName?: string;
  align?: 'left' | 'right' | 'center';
}

export const DatePicker: React.FC<DatePickerProps> = ({
  selectedDate,
  onDateChange,
  availableDates: _availableDates = [],
  label,
  className = '',
  buttonClassName = '',
  align = 'center'
}) => {
  const [isOpen, setIsOpen] = useState(false);
  const [mode, setMode] = useState<'single' | 'month'>('single');

  // Selected single date state
  const [activeDay, setActiveDay] = useState<string>(selectedDate || '');

  useEffect(() => {
    setActiveDay(selectedDate || '');
  }, [selectedDate]);

  // Current view Month and Year
  const getInitialView = () => {
    if (selectedDate && selectedDate.includes('-')) {
      const parts = selectedDate.split('-').map(Number);
      if (parts[0] && parts[1]) {
        return { year: parts[0], month: parts[1] };
      }
    }
    const now = new Date();
    return { year: now.getFullYear(), month: now.getMonth() + 1 };
  };

  const initialView = getInitialView();
  const [viewYear, setViewYear] = useState<number>(initialView.year);
  const [viewMonth, setViewMonth] = useState<number>(initialView.month);

  const containerRef = useRef<HTMLDivElement>(null);

  // Click outside to close
  useEffect(() => {
    const handleClickOutside = (e: MouseEvent) => {
      if (containerRef.current && !containerRef.current.contains(e.target as Node)) {
        setIsOpen(false);
      }
    };
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);

  const today = new Date();
  const pad = (n: number) => String(n).padStart(2, '0');
  const todayStr = `${today.getFullYear()}-${pad(today.getMonth() + 1)}-${pad(today.getDate())}`;

  // Month navigation in Day view
  const handlePrevMonth = () => {
    if (viewMonth === 1) {
      setViewMonth(12);
      setViewYear(viewYear - 1);
    } else {
      setViewMonth(viewMonth - 1);
    }
  };

  const handleNextMonth = () => {
    if (viewMonth === 12) {
      setViewMonth(1);
      setViewYear(viewYear + 1);
    } else {
      setViewMonth(viewMonth + 1);
    }
  };

  const handlePrevYear = () => setViewYear(viewYear - 1);
  const handleNextYear = () => setViewYear(viewYear + 1);

  // Calendar Day Click Handler -> Select Date and Close
  const handleDayClick = (dateStr: string) => {
    setActiveDay(dateStr);
    onDateChange(dateStr);
    setIsOpen(false);
  };

  // Month Click Handler -> Jump to Day view of that month!
  const handleMonthClick = (mNum: number) => {
    setViewMonth(mNum);
    setMode('single'); // Jump automatically to day selection of that month!
  };

  // Calculations for calendar grid
  const getDaysInMonth = (year: number, month: number) => new Date(year, month, 0).getDate();
  const getFirstDayOfWeek = (year: number, month: number) => {
    const day = new Date(year, month - 1, 1).getDay(); // 0 = Sun
    return day;
  };

  const daysInCurrentMonth = getDaysInMonth(viewYear, viewMonth);
  const startDayOfWeek = getFirstDayOfWeek(viewYear, viewMonth);

  // Month names formatting
  const monthNamesEn = [
    'Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun',
    'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'
  ];

  // Helper date formatter for trigger button
  const formatTriggerText = () => {
    const dStr = activeDay || selectedDate;
    if (!dStr) return 'Chọn ngày';
    const [y, m, d] = dStr.split('-').map(Number);
    const dateObj = new Date(y, m - 1, d);
    const monthShort = dateObj.toLocaleString('en-US', { month: 'short' });
    return `${monthShort} ${d}, ${y}`;
  };

  const alignClass =
    align === 'left' ? 'left-0' :
    align === 'right' ? 'right-0' :
    'left-1/2 -translate-x-1/2';

  return (
    <div className={`relative inline-block font-outfit ${className}`} style={{ fontFamily: "'Outfit', sans-serif" }} ref={containerRef}>
      {label && <label className="block text-xs uppercase font-bold text-slate-400 mb-1 text-center font-outfit">{label}</label>}

      {/* Trigger Button - Thin Border, Rounded-xl (20%), Glassmorphism Glow Shadow */}
      <button
        type="button"
        onClick={() => setIsOpen(!isOpen)}
        className={`w-full flex items-center justify-center gap-2 px-3.5 py-2 rounded-xl bg-[#121519]/90 backdrop-blur-md border border-white/15 text-white font-semibold text-[13px] transition-all duration-200 hover:border-[#a3e635]/60 hover:bg-white/[0.04] text-center font-outfit shadow-lg ${buttonClassName}`}
        style={{ 
          fontFamily: "'Outfit', sans-serif",
          boxShadow: '0 4px 20px rgba(0,0,0,0.4), 0 0 15px rgba(163,230,53,0.08)'
        }}
      >
        <i className="fa-regular fa-calendar-days text-[#a3e635] text-sm shrink-0"></i>
        <span className="font-bold text-slate-100 tracking-tight text-[13px] text-center whitespace-nowrap font-outfit">
          {formatTriggerText()}
        </span>
        <i className={`fa-solid fa-chevron-down text-[10px] text-[#a3e635] shrink-0 transition-transform duration-200 ${isOpen ? 'rotate-180' : ''}`}></i>
      </button>

      {/* Popover Card - Thin Border, Rounded-xl, Glassmorphism Backdrop Blur & Glowing Shadow */}
      {isOpen && (
        <div
          className={`absolute top-full mt-2 z-[999] w-64 bg-[#121519]/95 backdrop-blur-2xl border border-white/15 rounded-xl p-3.5 text-white font-outfit ${alignClass}`}
          style={{ 
            fontFamily: "'Outfit', sans-serif", 
            boxShadow: '0 20px 40px -10px rgba(0,0,0,0.95), 0 0 25px rgba(163,230,53,0.15)' 
          }}
        >
          {/* Mode Switcher Tabs: 2 Tabs ONLY [ Ngày | Tháng ] */}
          <div className="flex bg-[#16191e]/90 p-1 rounded-lg mb-3 border border-white/10">
            <button
              type="button"
              onClick={() => setMode('single')}
              className={`flex-1 py-1.5 text-[11px] font-extrabold rounded-md text-center flex items-center justify-center transition-all font-outfit ${
                mode === 'single' ? 'bg-[#a3e635] text-black font-extrabold shadow-sm' : 'text-slate-400 hover:text-slate-200'
              }`}
            >
              Ngày
            </button>
            <button
              type="button"
              onClick={() => setMode('month')}
              className={`flex-1 py-1.5 text-[11px] font-extrabold rounded-md text-center flex items-center justify-center transition-all font-outfit ${
                mode === 'month' ? 'bg-[#a3e635] text-black font-extrabold shadow-sm' : 'text-slate-400 hover:text-slate-200'
              }`}
            >
              Tháng
            </button>
          </div>

          {/* DAY SELECTION VIEW */}
          {mode === 'single' && (
            <div>
              {/* Header: Click Month Year title to switch to Month View */}
              <div className="flex items-center justify-between mb-2.5 px-1 text-center">
                <button
                  type="button"
                  onClick={() => setMode('month')}
                  className="font-extrabold text-sm text-[#a3e635] hover:underline tracking-tight text-center font-outfit flex items-center gap-1"
                >
                  <span>{monthNamesEn[viewMonth - 1]} {viewYear}</span>
                  <i className="fa-solid fa-caret-down text-xs text-[#a3e635]"></i>
                </button>

                <div className="flex items-center gap-1">
                  <button
                    type="button"
                    onClick={handlePrevMonth}
                    className="w-6.5 h-6.5 flex items-center justify-center text-center rounded-md text-slate-400 hover:text-[#a3e635] hover:bg-white/10 transition-colors"
                  >
                    <i className="fa-solid fa-chevron-left text-xs"></i>
                  </button>
                  <button
                    type="button"
                    onClick={handleNextMonth}
                    className="w-6.5 h-6.5 flex items-center justify-center text-center rounded-md text-slate-400 hover:text-[#a3e635] hover:bg-white/10 transition-colors"
                  >
                    <i className="fa-solid fa-chevron-right text-xs"></i>
                  </button>
                </div>
              </div>

              {/* Days of Week Header: S M T W T F S */}
              <div className="grid grid-cols-7 text-center text-[11px] font-extrabold text-slate-400 mb-1.5 font-outfit">
                <span className="flex items-center justify-center">S</span>
                <span className="flex items-center justify-center">M</span>
                <span className="flex items-center justify-center">T</span>
                <span className="flex items-center justify-center">W</span>
                <span className="flex items-center justify-center">T</span>
                <span className="flex items-center justify-center">F</span>
                <span className="flex items-center justify-center">S</span>
              </div>

              {/* Day Grid - Perfect 1:1 Squares with Rounded Corners */}
              <div className="grid grid-cols-7 gap-0.5 text-center text-[13px] font-outfit">
                {/* Empty cells before month start */}
                {Array.from({ length: startDayOfWeek }).map((_, i) => (
                  <div key={`empty-${i}`} className="aspect-square w-full flex items-center justify-center" />
                ))}

                {/* Month Days */}
                {Array.from({ length: daysInCurrentMonth }).map((_, idx) => {
                  const dayNum = idx + 1;
                  const dateStr = `${viewYear}-${pad(viewMonth)}-${pad(dayNum)}`;
                  const isSelected = activeDay === dateStr;
                  const isToday = todayStr === dateStr;

                  // CSS classes: Perfect 1:1 Square Cells with Rounded Corners
                  let cellClasses = 'aspect-square w-full flex items-center justify-center text-center text-[13px] font-extrabold leading-none rounded-md transition-all font-outfit ';

                  if (isSelected) {
                    cellClasses += 'bg-[#a3e635] text-black font-black z-10 shadow-sm ';
                  } else if (isToday) {
                    cellClasses += 'border border-[#a3e635] text-[#a3e635] font-black hover:bg-[#a3e635]/15 ';
                  } else {
                    cellClasses += 'text-slate-200 hover:bg-white/10 hover:text-[#a3e635] ';
                  }

                  return (
                    <button
                      key={dayNum}
                      type="button"
                      onClick={() => handleDayClick(dateStr)}
                      className={cellClasses}
                      style={{ fontFamily: "'Outfit', sans-serif" }}
                    >
                      <span className="flex items-center justify-center text-center leading-none font-outfit">{dayNum}</span>
                    </button>
                  );
                })}
              </div>
            </div>
          )}

          {/* PERFECT SQUARE 4x3 MONTH GRID -> Click month jumps to Day view of that month */}
          {mode === 'month' && (
            <div>
              <div className="flex items-center justify-between mb-2.5 px-1 text-center">
                <span className="font-extrabold text-sm text-[#a3e635] tracking-wider text-center font-outfit">
                  NĂM {viewYear}
                </span>

                <div className="flex items-center gap-1">
                  <button
                    type="button"
                    onClick={handlePrevYear}
                    className="w-6.5 h-6.5 flex items-center justify-center text-center rounded-md text-slate-400 hover:text-[#a3e635] hover:bg-white/10"
                  >
                    <i className="fa-solid fa-chevron-left text-xs"></i>
                  </button>
                  <button
                    type="button"
                    onClick={handleNextYear}
                    className="w-6.5 h-6.5 flex items-center justify-center text-center rounded-md text-slate-400 hover:text-[#a3e635] hover:bg-white/10"
                  >
                    <i className="fa-solid fa-chevron-right text-xs"></i>
                  </button>
                </div>
              </div>

              {/* 4 Columns x 3 Rows 1:1 Perfect Squares */}
              <div className="grid grid-cols-4 gap-1 text-center font-outfit">
                {monthNamesEn.map((name, idx) => {
                  const monthNum = idx + 1;
                  const isCurrentMonthView = viewMonth === monthNum;

                  return (
                    <button
                      key={monthNum}
                      type="button"
                      onClick={() => handleMonthClick(monthNum)}
                      className={`aspect-square w-full rounded-lg text-center flex items-center justify-center transition-all font-outfit ${
                        isCurrentMonthView
                          ? 'bg-[#a3e635] text-black font-black shadow-sm'
                          : 'bg-[#16191e]/90 text-slate-200 hover:bg-white/10 hover:text-[#a3e635] border border-white/10'
                      }`}
                      style={{ fontFamily: "'Outfit', sans-serif" }}
                    >
                      <span className="text-xs font-black tracking-tight text-center leading-none flex items-center justify-center font-outfit">{name}</span>
                    </button>
                  );
                })}
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
};
