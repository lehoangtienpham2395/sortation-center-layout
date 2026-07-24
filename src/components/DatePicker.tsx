import React, { useState, useEffect, useRef } from 'react';

export interface DatePickerProps {
  selectedDate: string; // "YYYY-MM-DD" or "YYYY-MM-DD..YYYY-MM-DD" or "YYYY-MM"
  onDateChange: (dateStr: string, isMonthMode?: boolean) => void;
  availableDates?: string[]; // Array of "YYYY-MM-DD"
  label?: string;
  className?: string;
  align?: 'left' | 'right' | 'center';
}

export const DatePicker: React.FC<DatePickerProps> = ({
  selectedDate,
  onDateChange,
  availableDates: _availableDates = [],
  label,
  className = '',
  align = 'center'
}) => {
  const [isOpen, setIsOpen] = useState(false);
  const [mode, setMode] = useState<'range' | 'single' | 'month'>('single');

  // Range selection draft state
  const [startDate, setStartDate] = useState<string>('');
  const [endDate, setEndDate] = useState<string>('');
  const [hoverDate, setHoverDate] = useState<string>('');

  const parseInitial = (str: string) => {
    if (!str) return { start: '', end: '' };
    if (str.includes('..')) {
      const [s, e] = str.split('..');
      return { start: s, end: e };
    }
    return { start: str, end: str };
  };

  useEffect(() => {
    const { start, end } = parseInitial(selectedDate);
    setStartDate(start);
    setEndDate(end);

    if (selectedDate && selectedDate.length === 7) {
      setMode('month');
    }
  }, [selectedDate]);

  // Current view Month and Year
  const getInitialView = () => {
    const base = startDate || selectedDate || '';
    if (base) {
      const parts = base.split('-').map(Number);
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

  // Month navigation
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

  // Calendar Day Click Handler (Range logic)
  const handleDayClick = (dateStr: string) => {
    if (mode === 'single') {
      setStartDate(dateStr);
      setEndDate(dateStr);
      onDateChange(dateStr, false);
      setIsOpen(false);
      return;
    }

    // Range Mode Selection
    if (!startDate || (startDate && endDate)) {
      // Step 1: Pick start date
      setStartDate(dateStr);
      setEndDate('');
    } else if (startDate && !endDate) {
      // Step 2: Pick end date
      if (dateStr < startDate) {
        setStartDate(dateStr);
        setEndDate(startDate);
        onDateChange(`${dateStr}..${startDate}`, false);
      } else if (dateStr === startDate) {
        setEndDate(dateStr);
        onDateChange(dateStr, false);
      } else {
        setEndDate(dateStr);
        onDateChange(`${startDate}..${dateStr}`, false);
      }
      setIsOpen(false);
    }
  };

  // Month selection handler
  const handleMonthClick = (mNum: number) => {
    const formatted = `${viewYear}-${pad(mNum)}`;
    onDateChange(formatted, true);
    setIsOpen(false);
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
    if (selectedDate && selectedDate.length === 7) {
      const [y, m] = selectedDate.split('-');
      return `Tháng ${m}, ${y}`;
    }

    const formatDateNice = (dStr: string) => {
      if (!dStr) return '';
      const [y, m, d] = dStr.split('-').map(Number);
      const dateObj = new Date(y, m - 1, d);
      const monthShort = dateObj.toLocaleString('en-US', { month: 'short' });
      return `${monthShort} ${d}, ${y}`;
    };

    if (startDate && endDate) {
      if (startDate === endDate) return formatDateNice(startDate);
      const [sy, , sd] = startDate.split('-').map(Number);
      const [ey, , ed] = endDate.split('-').map(Number);
      const sObj = new Date(sy, Number(startDate.split('-')[1]) - 1, sd);

      const sMonth = sObj.toLocaleString('en-US', { month: 'short' });

      if (sy === ey) {
        return `${sMonth} ${sd}–${ed}, ${ey}`;
      }
      return `${formatDateNice(startDate)}–${formatDateNice(endDate)}`;
    }

    if (startDate) return formatDateNice(startDate);
    return 'Chọn ngày';
  };

  const alignClass =
    align === 'left' ? 'left-0' :
    align === 'right' ? 'right-0' :
    'left-1/2 -translate-x-1/2';

  return (
    <div className={`relative inline-block font-outfit ${className}`} style={{ fontFamily: "'Outfit', sans-serif" }} ref={containerRef}>
      {label && <label className="block text-xs uppercase font-bold text-slate-400 mb-1 text-center font-outfit">{label}</label>}

      {/* Trigger Button - 100% Synced Dark Theme, Sharp Square 1:1, Outfit font */}
      <button
        type="button"
        onClick={() => setIsOpen(!isOpen)}
        className="w-full flex items-center justify-center gap-2 px-3.5 py-2 rounded-none bg-[#121519] border-2 border-[#a3e635]/60 text-white font-semibold text-[13px] transition-all shadow-md hover:border-[#a3e635] text-center font-outfit"
        style={{ fontFamily: "'Outfit', sans-serif" }}
      >
        <i className="fa-regular fa-calendar-days text-[#a3e635] text-sm shrink-0"></i>
        <span className="font-bold text-slate-100 tracking-tight text-[13px] text-center whitespace-nowrap font-outfit">
          {formatTriggerText()}
        </span>
        <i className={`fa-solid fa-chevron-down text-[10px] text-[#a3e635] shrink-0 transition-transform duration-200 ${isOpen ? 'rotate-180' : ''}`}></i>
      </button>

      {/* Popover Card - w-64, #121519, rounded-none */}
      {isOpen && (
        <div
          className={`absolute top-full mt-2 z-50 w-64 bg-[#121519] border border-[#2a2f38] rounded-none shadow-2xl p-3 text-white font-outfit ${alignClass}`}
          style={{ fontFamily: "'Outfit', sans-serif", boxShadow: '0 20px 40px -10px rgba(0,0,0,0.95), 0 0 25px rgba(163,230,53,0.1)' }}
        >
          {/* Mode Switcher Tabs */}
          <div className="flex bg-[#16191e] p-0.5 rounded-none mb-3 border border-[#232832]">
            <button
              type="button"
              onClick={() => setMode('single')}
              className={`flex-1 py-1.5 text-[11px] font-extrabold rounded-none text-center flex items-center justify-center transition-all font-outfit ${
                mode === 'single' ? 'bg-[#a3e635] text-black font-extrabold shadow-sm' : 'text-slate-400 hover:text-slate-200'
              }`}
            >
              Ngày
            </button>
            <button
              type="button"
              onClick={() => setMode('range')}
              className={`flex-1 py-1.5 text-[11px] font-extrabold rounded-none text-center flex items-center justify-center transition-all font-outfit ${
                mode === 'range' ? 'bg-[#a3e635] text-black font-extrabold shadow-sm' : 'text-slate-400 hover:text-slate-200'
              }`}
            >
              Khoảng
            </button>
            <button
              type="button"
              onClick={() => setMode('month')}
              className={`flex-1 py-1.5 text-[11px] font-extrabold rounded-none text-center flex items-center justify-center transition-all font-outfit ${
                mode === 'month' ? 'bg-[#a3e635] text-black font-extrabold shadow-sm' : 'text-slate-400 hover:text-slate-200'
              }`}
            >
              Tháng
            </button>
          </div>

          {/* DAY RANGE & SINGLE VIEW */}
          {(mode === 'range' || mode === 'single') && (
            <div>
              {/* Header: Month Year Title & Navigation Chevrons */}
              <div className="flex items-center justify-between mb-2.5 px-1 text-center">
                <span className="font-extrabold text-sm text-[#a3e635] tracking-tight text-center font-outfit">
                  {monthNamesEn[viewMonth - 1]} {viewYear}
                </span>

                <div className="flex items-center gap-1">
                  <button
                    type="button"
                    onClick={handlePrevMonth}
                    className="w-6.5 h-6.5 flex items-center justify-center text-center rounded-none text-slate-400 hover:text-[#a3e635] hover:bg-[#1c2128] transition-colors"
                  >
                    <i className="fa-solid fa-chevron-left text-xs"></i>
                  </button>
                  <button
                    type="button"
                    onClick={handleNextMonth}
                    className="w-6.5 h-6.5 flex items-center justify-center text-center rounded-none text-slate-400 hover:text-[#a3e635] hover:bg-[#1c2128] transition-colors"
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

              {/* Day Grid - 1:1 Perfect Squares */}
              <div className="grid grid-cols-7 gap-0.5 text-center text-[13px] font-outfit">
                {/* Empty cells before month start */}
                {Array.from({ length: startDayOfWeek }).map((_, i) => (
                  <div key={`empty-${i}`} className="aspect-square w-full flex items-center justify-center" />
                ))}

                {/* Month Days */}
                {Array.from({ length: daysInCurrentMonth }).map((_, idx) => {
                  const dayNum = idx + 1;
                  const dateStr = `${viewYear}-${pad(viewMonth)}-${pad(dayNum)}`;

                  // Calculate selection states
                  const isStart = startDate === dateStr;
                  const isEnd = endDate === dateStr;

                  let activeEnd = endDate;
                  if (startDate && !endDate && hoverDate && hoverDate >= startDate) {
                    activeEnd = hoverDate;
                  }

                  const isRangeMiddle =
                    startDate && activeEnd && dateStr > startDate && dateStr < activeEnd;
                  const isToday = todayStr === dateStr;

                  // CSS classes
                  let cellClasses = 'aspect-square w-full flex items-center justify-center text-center text-[13px] font-extrabold leading-none rounded-none transition-all font-outfit ';

                  if (isStart || isEnd || dateStr === activeEnd) {
                    cellClasses += 'bg-[#a3e635] text-black font-black z-10 ';
                  } else if (isRangeMiddle) {
                    cellClasses += 'bg-[#a3e635]/25 text-[#f7fee7] font-bold ';
                  } else if (isToday) {
                    cellClasses += 'border-2 border-[#a3e635] text-[#a3e635] font-black hover:bg-[#a3e635]/15 ';
                  } else {
                    cellClasses += 'text-slate-200 hover:bg-[#1c2128] hover:text-[#a3e635] ';
                  }

                  return (
                    <button
                      key={dayNum}
                      type="button"
                      onClick={() => handleDayClick(dateStr)}
                      onMouseEnter={() => setHoverDate(dateStr)}
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

          {/* PERFECT SQUARE 4x3 MONTH GRID */}
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
                    className="w-6.5 h-6.5 flex items-center justify-center text-center rounded-none text-slate-400 hover:text-[#a3e635] hover:bg-[#1c2128]"
                  >
                    <i className="fa-solid fa-chevron-left text-xs"></i>
                  </button>
                  <button
                    type="button"
                    onClick={handleNextYear}
                    className="w-6.5 h-6.5 flex items-center justify-center text-center rounded-none text-slate-400 hover:text-[#a3e635] hover:bg-[#1c2128]"
                  >
                    <i className="fa-solid fa-chevron-right text-xs"></i>
                  </button>
                </div>
              </div>

              {/* 4 Columns x 3 Rows 1:1 Perfect Squares */}
              <div className="grid grid-cols-4 gap-1 text-center font-outfit">
                {monthNamesEn.map((name, idx) => {
                  const monthNum = idx + 1;
                  const monthStr = `${viewYear}-${pad(monthNum)}`;
                  const isSelected = selectedDate === monthStr;

                  return (
                    <button
                      key={monthNum}
                      type="button"
                      onClick={() => handleMonthClick(monthNum)}
                      className={`aspect-square w-full rounded-none text-center flex items-center justify-center transition-all font-outfit ${
                        isSelected
                          ? 'bg-[#a3e635] text-black font-black shadow-sm'
                          : 'bg-[#16191e] text-slate-200 hover:bg-[#1c2128] hover:text-[#a3e635] border border-[#232832]'
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
