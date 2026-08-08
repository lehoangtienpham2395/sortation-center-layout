import RouteMapDashboard from './components/RouteMapDashboard';
import { useState, useEffect, useMemo, useRef } from 'react';
import InboundDashboard from './components/InboundDashboard';
import HeatmapDashboard from './components/HeatmapDashboard';
import KpiDashboard from './components/KpiDashboard';
import { DatePicker } from './components/DatePicker';
import { getTodayOpDate, getFormattedVietnamTime } from './utils/dateUtils';
import { Menu, RotateCw } from 'lucide-react';
import configData from './data/config.json';

// Animated Number Ticker Component (Smooth Transition Without 0 Flash)
function NumberTicker({ value }: { value: number }) {
  const ref = useRef<HTMLSpanElement>(null);
  const prevValRef = useRef<number>(value);

  useEffect(() => {
    const start = prevValRef.current;
    const end = value;
    prevValRef.current = value;

    if (start === end) {
      if (ref.current) ref.current.textContent = end.toLocaleString();
      return;
    }
    const duration = 0.4; // seconds
    let startTime: number | null = null;
    
    const animateCount = (timestamp: number) => {
      if (!startTime) startTime = timestamp;
      const progress = Math.min((timestamp - startTime) / (duration * 1000), 1);
      const current = Math.floor(progress * (end - start) + start);
      if (ref.current) {
        ref.current.textContent = current.toLocaleString();
      }
      if (progress < 1) {
        window.requestAnimationFrame(animateCount);
      }
    };
    
    window.requestAnimationFrame(animateCount);
  }, [value]);

  return <span ref={ref}>{value.toLocaleString()}</span>;
}

const MASTER_CONFIG_MAP: { [key: string]: string } = {};
try {
  const items = Array.isArray(configData) 
    ? configData 
    : ((configData as any)?.default || (configData as any)?.valid || []);
  if (Array.isArray(items)) {
    items.forEach((c: any) => {
      const key = c?.AreaID || c?.areaId || c?.Station_1;
      const name = c?.['Bưu cục'] || c?.buuCuc || c?.Station_2;
      if (key && name) {
        MASTER_CONFIG_MAP[String(key).trim()] = String(name).trim();
      }
    });
  }
} catch (e) {
  console.error("Error loading master config map:", e);
}


// ── Rack / chute definitions (Chuẩn hóa 100% tên bưu cục theo valid.csv) ──
const ZONE3_LIST = [
  // 5 ô chutes bên phải vách ngăn (vùng xanh lá)
  { areaId: 'C01', name: 'SG CHỢ LỚN', zone: 3 },
  { areaId: 'C02', name: 'SG HƯNG LONG', zone: 3 },
  { areaId: 'C03', name: 'SG BÌNH LỢI TRUNG', zone: 3 },
  { areaId: 'C04', name: 'SG BÌNH TRỊ ĐÔNG', zone: 3 },
  { areaId: 'C05', name: 'SG KHÁNH HỘI', zone: 3 },
  // 21 ô chutes bên trái vách ngăn (C06 -> C26)
  { areaId: 'C06', name: 'BD DĨ AN', zone: 3 },       { areaId: 'C07', name: 'DC GIA ĐỊNH', zone: 3 },
  { areaId: 'C08', name: 'TG GÒ CÔNG', zone: 3 },   { areaId: 'C09', name: 'LA HẬU NGHĨA', zone: 3 },
  { areaId: 'C10', name: 'SG XUÂN HÒA', zone: 3 },   { areaId: 'C11', name: 'LA CẦN ĐƯỚC', zone: 3 },
  { areaId: 'C12', name: 'SG PHÚ NHUẬN', zone: 3 },  { areaId: 'C13', name: 'ST VĨNH CHÂU', zone: 3 },
  { areaId: 'C14', name: 'CT LONG MỸ', zone: 3 },    { areaId: 'C15', name: 'ST PHÚ LỢI', zone: 3 },
  { areaId: 'C16', name: 'SG NHƠN ĐỨC', zone: 3 },   { areaId: 'C17', name: 'VL CHỢ LÁCH', zone: 3 },
  { areaId: 'C18', name: 'AG AN PHÚ', zone: 3 },     { areaId: 'C19', name: 'AG TÂN CHÂU', zone: 3 },
  { areaId: 'C20', name: 'AG TỊNH BIÊN', zone: 3 },  { areaId: 'C21', name: 'AG THOẠI SƠN', zone: 3 },
  { areaId: 'C22', name: 'VT LONG ĐẤT', zone: 3 },   { areaId: 'C23', name: 'SG BẢY HIỀN', zone: 3 },
  { areaId: 'C24', name: 'BD BÌNH HÒA', zone: 3 },
  { areaId: 'C25', name: 'LA BẾN LỨC', zone: 3 },
  { areaId: 'C26', name: '3PL', zone: 3 }
];

const ZONE3_TRUCKS = Array.from({ length: 24 }, (_, i) => ({
  areaId: `T3-${String(24 - i).padStart(2, '0')}`,
  name: `TẢI Chờ 3-${String(24 - i).padStart(2, '0')}`,
  zone: 3
}));

const ZONE2_LIST = [
  // 5 ô chutes bên phải vách ngăn (vùng màu vàng)
  { areaId: 'A00', name: 'VT LONG ĐẤT', zone: 3 },
  { areaId: 'A01', name: 'SG HÓC MÔN', zone: 3 },
  { areaId: 'A02', name: 'SG BÌNH LỢI', zone: 3 },
  { areaId: 'A03', name: 'SG TÂN THỚI HIỆP', zone: 3 },
  { areaId: 'A04', name: 'LA ĐỨC HÒA', zone: 3 },
  // 18 ô chutes bên trái vách ngăn (B01 -> B18)
  { areaId: 'B01', name: 'SG ĐÔNG HƯNG THUẬN', zone: 2 }, { areaId: 'B02', name: 'SG TÂN HƯNG', zone: 2 },
  { areaId: 'B03', name: 'SG BÌNH TÂN', zone: 2 },         { areaId: 'B04', name: 'SG AN LẠC', zone: 2 },
  { areaId: 'B05', name: 'SG PHÚ LÂM', zone: 2 },          { areaId: 'B06', name: 'SG HIỆP BÌNH', zone: 2 },
  { areaId: 'B07', name: 'SG TÂN SƠN NHÌ', zone: 2 },       { areaId: 'B08', name: 'SG CỦ CHI', zone: 2 },
  { areaId: 'B09', name: 'SG TÂN TẠO', zone: 2 },          { areaId: 'B10', name: 'SG GÒ VẤP', zone: 2 },
  { areaId: 'B11', name: 'SG AN PHÚ ĐÔNG', zone: 2 },      { areaId: 'B12', name: 'VT CHÂU ĐỨC', zone: 2 },
  { areaId: 'B13', name: 'VT XUYÊN MỘC', zone: 2 },        { areaId: 'B14', name: 'SG VĨNH LỘC', zone: 2 },
  { areaId: 'B15', name: 'SG TÂN NHỰT', zone: 2 },         { areaId: 'B16', name: 'SG BÀ ĐIỂM', zone: 2 }
];

const ZONE2_TRUCKS = Array.from({ length: 21 }, (_, i) => {
  const num = 21 - i;
  return {
    areaId: `T2-${String(num).padStart(2, '0')}`,
    name: `TẢI Chờ 2-${String(num).padStart(2, '0')}`,
    zone: num >= 17 ? 3 : 2
  };
});

const ZONE1_LIST = [
  // 15 ô chutes bên trái vách ngăn (A06 -> A20, loại bỏ A03, A04 để tránh trùng lặp với Zone 2)
  { areaId: 'A06', name: 'BN HUB', zone: 1 },
  { areaId: 'A07', name: 'CT Ô MÔN', zone: 1 },       { areaId: 'A08', name: 'CT BÌNH THỦY', zone: 1 },
  { areaId: 'A09', name: 'CT NINH KIỀU', zone: 1 },   { areaId: 'A10', name: 'DT CAO LÃNH', zone: 1 },
  { areaId: 'A11', name: 'DT SA ĐÉC', zone: 1 },      { areaId: 'A12', name: 'TG HÒA KHÁNH', zone: 1 },
  { areaId: 'A13', name: 'VL VĨNH LONG', zone: 1 },   { areaId: 'A14', name: 'TG AN HỮU', zone: 1 },
  { areaId: 'A15', name: 'LA TÂN AN', zone: 1 },      { areaId: 'A16', name: 'SG THỦ ĐỨC', zone: 1 },
  { areaId: 'A17', name: 'TG TRUNG AN', zone: 1 },    { areaId: 'A18', name: 'VT VŨNG TÀU', zone: 1 },
  { areaId: 'A19', name: 'AG LONG XUYÊN', zone: 1 },  { areaId: 'A20', name: 'AG CẦN ĐĂNG', zone: 1 }
];

const ZONE1_TRUCKS = Array.from({ length: 16 }, (_, i) => ({
  areaId: `T1-${String(16 - i).padStart(2, '0')}`,
  name: `TẢI Chờ 1-${String(16 - i).padStart(2, '0')}`,
  zone: 1
}));

const INBOUND_TRUCKS = [
  { areaId: 'TI-01', name: 'Bãi chờ nhập 01', zone: 4, bx: 663 },
  { areaId: 'TI-02', name: 'Bãi chờ nhập 02', zone: 4, bx: 691 },
  { areaId: 'TI-03', name: 'Bãi chờ nhập 03', zone: 4, bx: 719 },
  { areaId: 'TI-04', name: 'Bãi chờ nhập 04', zone: 4, bx: 747 },
  { areaId: 'TI-05', name: 'Bãi chờ nhập 05', zone: 4, bx: 775 },
  { areaId: 'TI-06', name: 'Bãi chờ nhập 06', zone: 4, bx: 803 }
];

const CHUTE_RACKS = [...ZONE3_LIST, ...ZONE2_LIST, ...ZONE1_LIST];
const ALL_RACKS = [...CHUTE_RACKS, ...ZONE3_TRUCKS, ...ZONE2_TRUCKS, ...ZONE1_TRUCKS, ...INBOUND_TRUCKS];

ALL_RACKS.forEach(item => {
  if (MASTER_CONFIG_MAP[item.areaId]) {
    item.name = MASTER_CONFIG_MAP[item.areaId];
  }
});

function generateEmptyData() {
  return ALL_RACKS.reduce((acc, curr) => {
    const capacity = curr.areaId === 'A06' ? 1400 : 780;
    acc[curr.areaId] = { current: 0, capacity, remaining: capacity, utilization: 0, bucket: 'green', name: curr.name, weight: 0 };
    return acc;
  }, {} as any);
}



interface SheetRow {
  zone: string;
  areaId: string;
  buuCuc: string;
  volume: number;
  weight: number;
  capacity: number;
  date: string;
  type: string;
  status?: string;
}

// ════════════════════════════════════════════════════════════════════
// ⚠️ HỢP ĐỒNG DỮ LIỆU BACKEND ↔ FRONTEND (single source of truth)
// ════════════════════════════════════════════════════════════════════
// backend_sync/sync_postgre.py xuất `status`/`inv_status`/`drop_type` dưới dạng
// giá trị HIỂN THỊ SẴN (display-ready): 'Inbound', 'Transporting', 'Pickup Done',
// 'Created', 'Outbound', 'Rớt hôm nay', 'Rớt hôm trước' — khớp trực tiếp với các
// chuỗi so sánh cứng trong InboundDashboard.tsx.
//
// 2 bảng dưới đây là LỚP AN TOÀN DỰ PHÒNG (không phải lớp dịch bắt buộc):
// nếu backend lỡ đổi về dạng snake_case (vd 'inbound', 'rot_today') hoặc dữ liệu
// cũ từ Google Sheet còn sót lại, map vẫn tự quy về đúng giá trị UI cần — tránh
// lặp lại lỗi cũ (dashboard sai âm thầm, không báo lỗi).
//
// ➜ Nguyên tắc bắt buộc: MỌI so sánh status/drop_type trong toàn bộ app phải đi
//   qua normalizeStatus()/normalizeDropType(), KHÔNG so sánh chuỗi cứng rải rác
import {
  KEY_MAP,
  normalizeStatus,
  normalizeDropType
} from './contracts/data_contract';



function getApiUrl(filename: string): string {
  const t = `${Date.now()}_${Math.floor(Math.random() * 100000)}`;
  return `./data/${filename}?t=${t}`;
}

// Replaced with robust implementation imported from ./utils/dateUtils

async function fetchInboundSheetData(sheetType: 'Forecast' | 'Dispatch' | 'Inbound' | 'Linehaul' | 'Arrival' | 'Truck_ETA'): Promise<any[] | null> {
  try {
    let rawData: any = null;

    if (!rawData) {
      const t = `${Date.now()}_${Math.floor(Math.random() * 100000)}`;
      const fetchOpts: RequestInit = { cache: 'no-store', headers: { 'Cache-Control': 'no-cache, no-store, must-revalidate', 'Pragma': 'no-cache' } };
      const baseUrl = getApiUrl(`${sheetType.toLowerCase()}.json`);
      const cacheBustUrl = baseUrl.includes('?') ? `${baseUrl}&t=${t}` : `${baseUrl}?t=${t}`;
      let response = await fetch(cacheBustUrl, fetchOpts);
      if (!response.ok) {
        response = await fetch(`https://raw.githubusercontent.com/lehoangtienpham2395/sortation-center-layout/main/data/${sheetType.toLowerCase()}.json?t=${t}`, fetchOpts);
      }
      if (!response.ok) throw new Error(`HTTP ${response.status} fetching ${sheetType}`);
      rawData = await response.json();
    }
    const data = Array.isArray(rawData) ? rawData : (rawData?.trucks || rawData?.pivot_data || rawData?.data || []);
    
    return data.map((row: Record<string, any>) => {
      const out: Record<string, any> = { ...row };
      for (const [k, v] of Object.entries(row)) {
        if (KEY_MAP[k]) {
          out[KEY_MAP[k]] = v;
        }
      }
      if (out['Trạng thái'] !== undefined) {
        out['Trạng thái'] = normalizeStatus(out['Trạng thái']);
      }
      if (out['status'] !== undefined) {
        out['status'] = normalizeStatus(out['status']);
      }
      if (out['Loại rớt'] !== undefined) {
        out['Loại rớt'] = normalizeDropType(out['Loại rớt']);
      }
      if (out['drop_type'] !== undefined) {
        out['drop_type'] = normalizeDropType(out['drop_type']);
      }
      return out;
    });
  } catch (error) {
    console.error(`Error fetching inbound sheet ${sheetType}:`, error);
    return null;
  }
}

async function fetchMicroJson<T>(fileName: string, targetDate?: string): Promise<T | null> {
  try {
    const t = `${Date.now()}_${Math.floor(Math.random() * 100000)}`;
    const fetchOpts: RequestInit = { cache: 'no-store', headers: { 'Cache-Control': 'no-cache, no-store, must-revalidate', 'Pragma': 'no-cache' } };
    
    const todayStr = getTodayOpDate();
    const isHistory = Boolean(targetDate && targetDate < todayStr);
    const subPath = isHistory ? `history/${targetDate}` : 'live';

    let baseUrl = getApiUrl(`${subPath}/${fileName}`);
    let cacheBustUrl = baseUrl.includes('?') ? `${baseUrl}&t=${t}` : `${baseUrl}?t=${t}`;
    let response = await fetch(cacheBustUrl, fetchOpts);

    if (!response.ok) {
      // Fallback to GitHub Raw for exact subPath
      const rawUrl = `https://raw.githubusercontent.com/lehoangtienpham2395/sortation-center-layout/main/data/${subPath}/${fileName}?t=${t}`;
      response = await fetch(rawUrl, fetchOpts);
    }

    if (!response.ok && !isHistory) {
      // Fallback to root directory only for live today
      baseUrl = getApiUrl(fileName);
      cacheBustUrl = baseUrl.includes('?') ? `${baseUrl}&t=${t}` : `${baseUrl}?t=${t}`;
      response = await fetch(cacheBustUrl, fetchOpts);
    }

    if (!response.ok) return null;
    return await response.json();
  } catch (err) {
    console.warn(`Error fetching micro-JSON ${fileName} for targetDate=${targetDate}:`, err);
    return null;
  }
}

async function fetchSheetData(sheetType: string = 'Outbound'): Promise<SheetRow[] | null> {
  try {
    const todayStr = new Date().toISOString().split('T')[0];
    const t = `${Date.now()}_${Math.floor(Math.random() * 100000)}`;
    const fetchOpts: RequestInit = { cache: 'no-store', headers: { 'Cache-Control': 'no-cache, no-store, must-revalidate', 'Pragma': 'no-cache' } };
    const baseUrl = getApiUrl(`${sheetType.toLowerCase()}.json`);
    const cacheBustUrl = baseUrl.includes('?') ? `${baseUrl}&t=${t}` : `${baseUrl}?t=${t}`;
    let response = await fetch(cacheBustUrl, fetchOpts);
    if (!response.ok && getApiUrl('').startsWith('./')) {
      response = await fetch(`https://raw.githubusercontent.com/lehoangtienpham2395/sortation-center-layout/main/data/${sheetType.toLowerCase()}.json?t=${t}`, fetchOpts);
    }
    if (!response.ok) throw new Error(`HTTP ${response.status} fetching ${sheetType}`);
    const rawData = await response.json();
    const data = Array.isArray(rawData) ? rawData : (rawData?.pivot_data || rawData?.data || []);
    if (sheetType.toLowerCase() === 'heatmap') {
      return data;
    }

    const rows: SheetRow[] = [];

    // NOTE: status ở đây dùng chung BACKEND_STATUS_MAP (khai báo phía trên) —
    // KHÔNG khai báo map riêng nữa để tránh lệch với Inbound dashboard.
    for (const item of data) {
      const zone       = String(item['zone'] ?? item['Zone'] ?? item['round'] ?? item['Round'] ?? '');
      const areaId     = String(item['areaId'] ?? item['area_id'] ?? item['AreaID'] ?? item['rank'] ?? item['Rank'] ?? '');
      const buuCuc     = String(item['station_name'] ?? item['Bu cc'] ?? item['Bưu cục'] ?? item['name'] ?? item['Next_station'] ?? item['Pickup_station'] ?? '');
      const volumeRaw  = item['volume'] ?? item['Volume'] ?? item['Orders_num'];
      const volume     = Number(volumeRaw) || 0;
      const weightRaw  = item['weight_ton'] ?? item['weight'] ?? item['Weight'] ?? item['Orders_weight'] ?? item['weight_kg'];
      const capRaw     = item['capacity'] ?? item['Sc cha'] ?? item['Sức chứa'] ?? 780;
      const dateRaw    = item['op_date'] ?? item['Ngy'] ?? item['Ngày'] ?? item['date'] ?? item['operation_date_created'] ?? item['operation_date'] ?? item['operation_date_inbound'] ?? todayStr;
      const rawSt      = item['status'] ?? item['Trng thi'] ?? item['Trạng thái'] ?? item['status_sys'] ?? undefined;
      const statusRaw  = normalizeStatus(rawSt);

      let weight     = parseFloat(String(weightRaw ?? 0)) || 0;
      if (item['weight_kg'] !== undefined && item['weight_ton'] === undefined) {
        weight       = parseFloat(String(item['weight_kg'])) / 1000.0;
      }
      const capacity = Number(capRaw) || 780;

      if (areaId || buuCuc) {
        rows.push({
          zone: (zone && zone !== 'None') ? zone : 'ZONE 1',
          areaId: (areaId && areaId !== 'None') ? areaId : 'A01',
          buuCuc,
          volume: isNaN(volume) ? 1 : volume,
          weight,
          capacity,
          date: String(dateRaw),
          type: sheetType,
          status: statusRaw ? String(statusRaw) : undefined
        });
      }
    }
    return rows;
  } catch (error) {
    console.error('Error fetching sheet data:', error);
    return null;
  }
}


const UTILCOL: any = { green:'#10b981', yellow:'#f59e0b', orange:'#f97316', red:'#ef4444', darkred:'#dc2626' };

const WL = 60;                        
const WR = 894;                       
const WT = 30;                        
const WB = 508;                       

const A12_X = 390;                    
const A23_X = 642;                    

const Z_R = 838;                    
const Z_W = 700;                      
const Z_L = Z_R - Z_W;                

const Z1_W = 476;                     
const Z1_L = 642 - Z1_W;              

const Z_H = 56;                       
const TR_BAY_W = 28;                  

const PASS1_Y = 72;                  
const PASS1_H = 42;
const Z3_Y = 118;                     
const EW_Y = 234;                     
const EW_H = 42;
const Z2_Y = 336;                     
const EW2_Y = 396;                    
const EW2_H = 42;
const Z1_Y = 452;                     

const NS_X = 859;
const NS_W = 35;

const IB_Y = 452;                     
const IB_H = 56;
const IB_LW = 42;                     
const IB_SW = 8.4;                    
const IB_XL1 = 701;                   
const IB_XL2 = 772;                   
const IB_NAMES = ['A', 'AA', 'B', 'C', 'BN HUB'];

const DOCK_Y = WB;
const DOCK_H = 55;

function ZoneCell({ c, d, bx, by, bw, bh, midLabelY, isHovered, isMatched, onEnter, onLeave, onClick, addCenterLine, isTruck }:
  { c:any, d:any, bx:number, by:number, bw:number, bh:number, midLabelY:number,
    isHovered:boolean, isMatched?:boolean, onEnter:()=>void, onLeave:()=>void, onClick?:()=>void, addCenterLine?:boolean, isTruck?:boolean }) {
  const zoneColors: Record<number, string> = {
    4: 'var(--inbound)',
    3: 'var(--green)',
    2: 'var(--yellow)',
    1: 'var(--orange)'
  };
  const col = isTruck ? (c.zone === 4 ? 'rgba(96,165,250,0.4)' : 'rgba(255,255,255,0.2)') : (zoneColors[c.zone] || '#374151');
  const fillH = (bh - 2) * Math.min(d.utilization, 110) / 110;
  return (
    <g onMouseEnter={onEnter} onMouseLeave={onLeave} onClick={onClick} className="cursor-pointer">
      <rect x={bx} y={by} width={bw} height={bh}
            fill={isMatched ? '#00e5ff' : (isTruck ? (isHovered ? 'rgba(255,255,255,0.08)' : 'rgba(255,255,255,0.02)') : col)}
            fillOpacity={isMatched ? 0.6 : (isTruck ? 1 : (isHovered ? 0.35 : 0.14))}
            stroke={isMatched ? '#00e5ff' : col} strokeWidth={isMatched ? "2" : "0.7"} />
      {isMatched && (
        <rect x={bx-2} y={by-2} width={bw+4} height={bh+4} fill="none" stroke="#00e5ff" strokeWidth="1.5" strokeDasharray="3 2" className="animate-pulse" />
      )}
      {!isTruck && (
        <rect x={bx+1} y={by + bh - 1 - fillH} width={bw-2} height={fillH}
              fill={isMatched ? '#00e5ff' : col} fillOpacity={0.7} />
      )}
      {addCenterLine && !isTruck && (
        <line x1={bx+bw/2} y1={by+4} x2={bx+bw/2} y2={by+bh-4}
              stroke={col} strokeWidth="0.9" strokeDasharray="3 2" strokeOpacity="0.7" />
      )}
      <text x={bx+bw/2} y={midLabelY} textAnchor="middle" fill={isTruck ? 'rgba(255,255,255,0.5)' : '#fff'}
            className="font-sans text-[5px] font-bold tracking-wider"
            transform={`rotate(-90 ${bx+bw/2} ${midLabelY})`}
            pointerEvents="none">{c.name}</text>
      <text x={bx+bw/2} y={by-4} textAnchor="middle"
            fill={isMatched ? '#00e5ff' : (isHovered ? '#fff' : (isTruck ? 'rgba(255,255,255,0.4)' : 'rgba(154,167,194,0.7)'))}
            className="mono text-[5.5px] font-medium" pointerEvents="none">{c.areaId}</text>
    </g>
  );
}

const normalizeDateStr = (dStr: string): string => {
  if (!dStr) return '';
  const str = String(dStr).trim();
  if (/^\d{4}-\d{2}-\d{2}/.test(str)) return str.slice(0, 10);
  const dt = new Date(str);
  if (!isNaN(dt.getTime())) {
    const yyyy = dt.getFullYear();
    const mm = String(dt.getMonth() + 1).padStart(2, '0');
    const dd = String(dt.getDate()).padStart(2, '0');
    return `${yyyy}-${mm}-${dd}`;
  }
  return str.slice(0, 10);
};

const isDateMatch = (rDate: string, sDate: string) => {
  if (!sDate) return true;
  if (!rDate) return false;
  const normR = normalizeDateStr(rDate);
  const normS = normalizeDateStr(sDate);
  if (sDate.includes('..')) {
    const [start, end] = sDate.split('..');
    return normR >= normalizeDateStr(start) && normR <= normalizeDateStr(end);
  }
  return normR === normS;
};

export default function App() {
  const [isMobile, setIsMobile] = useState(window.innerWidth < 768);
  const [sidebarHovered, setSidebarHovered] = useState(false);
  const [currentView, setCurrentView] = useState<'master' | 'inbound' | 'heatmap' | 'kpi' | 'maps'>('inbound');
  const [inboundData, setInboundData] = useState<any[]>([]);
  const [linehaulData, setLinehaulData] = useState<any[]>([]);
  const [arrivalData, setArrivalData] = useState<any[]>([]);
  const [truckEtaData, setTruckEtaData] = useState<any[]>([]);
  // 🎯 Phân biệt lần đầu load (auto = todayOpDate) vs user chủ động chọn ngày
  const userChangedInboundDate = useRef(false);
  /** Gọi khi user bấm chọn ngày trên DatePicker Inbound */
  const handleInboundDateChange = (d: string) => {
    userChangedInboundDate.current = true;
    setSelectedInboundDate(d);
  };
  const [selectedInboundDate, setSelectedInboundDate] = useState<string>(() => getTodayOpDate());
  const [showMonitor, setShowMonitor] = useState(true);
  const [showTelemetry, setShowTelemetry] = useState(true);
  const [showControls, setShowControls] = useState(true);
  const [showTop10, setShowTop10] = useState(true);
  const [activeTab, setActiveTab] = useState<'layout' | 'inbound' | 'top10' | 'stats' | 'heatmap' | 'kpi'>('inbound');
  const [bottomSheetOpen, setBottomSheetOpen] = useState(false);
  const [data,       setData]       = useState<any>(generateEmptyData());
  const [utilTotal,  setUtilTotal]  = useState('0.0');
  const [free,       setFree]       = useState(0);
  const [usedCells,  setUsedCells]  = useState(0);
  const [totalOrders,setTotalOrders]= useState(0);

  const [totalWeight,setTotalWeight] = useState(0);
  const [hoveredRack,setHoveredRack]= useState<any>(null);
  const [tickerText, setTickerText] = useState('HỆ THỐNG ỔN ĐỊNH — KHÔNG CÓ CẢNH BÁO');
  const [loading,    setLoading]    = useState(false);
  const [hoveredZone,setHoveredZone] = useState<number | null>(null);
  const [lastUpdate, setLastUpdate] = useState<string>('');
  const [lastUpdateObj, setLastUpdateObj] = useState<any>(null);

  // Micro-JSON v2.0 State
  const [microKpiSummary, setMicroKpiSummary]     = useState<any | null>(null);
  const [microHourlyTrend, setMicroHourlyTrend]   = useState<any | null>(null);
  const [microOrdersStatus, setMicroOrdersStatus] = useState<any | null>(null);
  const [microTruckEta, setMicroTruckEta]         = useState<any | null>(null);
  const [microOriginStation, setMicroOriginStation] = useState<any | null>(null);


  // State variables for historic date/type filter
  const [rawSheetRows, setRawSheetRows] = useState<SheetRow[]>([]);
  const [heatmapRows, setHeatmapRows] = useState<any[]>([]);
  const [availableDates, setAvailableDates] = useState<string[]>([]);
  const [, setInboundAvailableDates] = useState<string[]>([]);
  const [selectedDate, setSelectedDate] = useState<string>('');
  const [selectedType, setSelectedType] = useState<'Outbound' | 'Backlog' | 'Backlog CAP 6AM' | 'Inventory' | 'Volume'>('Outbound');
  const [outboundRate, setOutboundRate] = useState<string>('0.0');
  const INVENTORY_STATUSES = ['Inbound', 'Transporting', 'Pickup Done', 'Created'];
  const [selectedStatuses, setSelectedStatuses] = useState<string[]>([...INVENTORY_STATUSES]);

  const [selectedDetailRack, setSelectedDetailRack] = useState<any | null>(null);

  const toggleStatus = (status: string) => {
    setSelectedStatuses(prev =>
      prev.includes(status) ? prev.filter(s => s !== status) : [...prev, status]
    );
  };

  const toggleAllStatuses = () => {
    if (selectedStatuses.length === INVENTORY_STATUSES.length) {
      setSelectedStatuses([]);
    } else {
      setSelectedStatuses([...INVENTORY_STATUSES]);
    }
  };

  // Dynamic labels based on selectedType — ô lớn luôn hiển thị TỈ LỆ LẤP ĐẦY
  const displayUtilizationLabel = 'TỈ LỆ LẤP ĐẦY';
  const displayUtilizationLabelLc = selectedType === 'Outbound' ? 'Tỉ lệ Outbound' : '% Lấp đầy';

    // Calculate statistics for Zone 1, 2, 3 (Zone 1 includes BN HUB A19)
  const zoneStats = useMemo(() => {
    const stats: Record<number, { current: number; capacity: number; backlog: number; weight: number; fillRate: number | string }> = {
      1: { current: 0, capacity: 0, backlog: 0, weight: 0, fillRate: 0 },
      2: { current: 0, capacity: 0, backlog: 0, weight: 0, fillRate: 0 },
      3: { current: 0, capacity: 0, backlog: 0, weight: 0, fillRate: 0 }
    };

    CHUTE_RACKS.forEach(c => {
      const d = data[c.areaId];
      if (d && c.zone) {
        stats[c.zone].current += d.current;
        stats[c.zone].capacity += d.capacity;
        stats[c.zone].backlog += d.backlogCurrent ?? 0;
        stats[c.zone].weight += d.weight ?? 0;
      }
    });

    const totalOrdersOfSelectedType = Object.values(data).reduce((acc, d: any) => acc + d.current, 0) as number;
    const grandTotal = stats[1].current + stats[2].current + stats[3].current;

    [1, 2, 3].forEach(z => {
      const s = stats[z];
      if (selectedType === 'Outbound') {
        s.fillRate = totalOrdersOfSelectedType > 0 ? ((s.current / totalOrdersOfSelectedType) * 100).toFixed(2) : '0.00';
      } else {
        s.fillRate = s.capacity > 0 ? Math.round((s.current / s.capacity) * 100) : 0;
      }
      (s as any).totalShare = grandTotal > 0 ? ((s.current / grandTotal) * 100).toFixed(1) : '0.0';
    });

    return stats;
  }, [data, selectedType]);

  const fetchAndUpdateData = async () => {
    setLoading(true);
    const currentLoadTime = getFormattedVietnamTime();
    setLastUpdate(currentLoadTime);
    lastUpdateTimestampRef.current = currentLoadTime;

    userChangedInboundDate.current = false;
    const todayOpDate = getTodayOpDate();

    // 1. Fetch last_update.json ngay lập tức để lấy daily_snapshots & metadata
    try {
      const t = `${Date.now()}_${Math.floor(Math.random() * 100000)}`;
      const fetchOpts: RequestInit = { cache: 'no-store', headers: { 'Cache-Control': 'no-cache, no-store, must-revalidate', 'Pragma': 'no-cache' } };
      let res = await fetch(`data/last_update.json?t=${t}`, fetchOpts);
      if (!res.ok) {
        res = await fetch(`https://raw.githubusercontent.com/lehoangtienpham2395/sortation-center-layout/main/data/last_update.json?t=${t}`, fetchOpts);
      }
      if (res.ok) {
        const d = await res.json();
        if (d) {
          setLastUpdateObj(d);
          if (d.last_update) {
            setLastUpdate(d.last_update);
            lastUpdateTimestampRef.current = d.last_update;
          }
        }
      }
    } catch (err) {
      console.error('Error fetching last_update:', err);
    }

    // 2. Fetch toàn bộ dữ liệu song song (Bao gồm cả micro-JSONs) trong 1 lượt duy nhất để React render 1 lần duy nhất chuẩn 9.253 đơn
    const [
      outboundRows, backlogRows, inventoryRows,
      ibRows, lhRows, arrivalRows, truckEtaRows, heatmapData,
      kpiSummary, hourlyTrend, ordersStatus, truckEtaMicro, originStation
    ] = await Promise.all([
      fetchSheetData('Outbound'),
      fetchSheetData('Backlog'),
      fetchSheetData('Inventory'),
      fetchInboundSheetData('Inbound'),
      fetchInboundSheetData('Linehaul'),
      fetchInboundSheetData('Arrival'),
      fetchInboundSheetData('Truck_ETA'),
      fetchSheetData('Heatmap'),
      fetchMicroJson<any>('inbound_kpi_summary.json', selectedInboundDate),
      fetchMicroJson<any>('inbound_hourly_trend.json', selectedInboundDate),
      fetchMicroJson<any>('inbound_orders_status.json', selectedInboundDate),
      fetchMicroJson<any>('inbound_truck_eta.json', selectedInboundDate),
      fetchMicroJson<any>('inbound_origin_station.json', selectedInboundDate),
    ]);

    // 🎯 Set Micro Summary trước để Forecast có sẵn giá trị 9.253 ngay từ Frame đầu tiên
    if (kpiSummary) setMicroKpiSummary(kpiSummary);
    if (hourlyTrend) setMicroHourlyTrend(hourlyTrend);
    if (ordersStatus) setMicroOrdersStatus(ordersStatus);
    if (originStation) setMicroOriginStation(originStation);

    if (ibRows && ibRows.length > 0) setInboundData(ibRows);
    if (lhRows && lhRows.length > 0) setLinehaulData(lhRows);
    if (arrivalRows && arrivalRows.length > 0) setArrivalData(arrivalRows);

    let microTrucksLoaded = false;
    if (truckEtaMicro) {
      setMicroTruckEta(truckEtaMicro);
      const trucks = truckEtaMicro?.trucks;
      if (Array.isArray(trucks) && trucks.length > 0) {
        setTruckEtaData(trucks);
        microTrucksLoaded = true;
      }
    }

    // Fallback: chỉ dùng truck_eta.json nếu inbound_truck_eta.json không có trucks
    if (!microTrucksLoaded) {
      let finalTruckEta = truckEtaRows;
      if (!finalTruckEta || finalTruckEta.length === 0) {
        try {
          const t = `${Date.now()}_${Math.floor(Math.random() * 100000)}`;
          const r = await fetch(`https://raw.githubusercontent.com/lehoangtienpham2395/sortation-center-layout/main/data/truck_eta.json?t=${t}`, { cache: 'no-store' });
          if (r.ok) {
            const json = await r.json();
            finalTruckEta = Array.isArray(json) ? json : (json?.trucks || []);
          }
        } catch (e) {
          console.warn('Direct GitHub Raw truck_eta fallback error:', e);
        }
      }
      if (finalTruckEta && finalTruckEta.length > 0) setTruckEtaData(finalTruckEta);
    }
    if (heatmapData) {
      setHeatmapRows(heatmapData);
    }

    // 🗂️ Fetch history_index.json to discover all available historical dates
    let historyDates: string[] = [];
    try {
      const t = `${Date.now()}`;
      const historyIndexRes = await fetch(
        `${getApiUrl('history/history_index.json')}?t=${t}`,
        { cache: 'no-store', headers: { 'Cache-Control': 'no-cache, no-store, must-revalidate' } }
      ).catch(() => fetch(
        `https://raw.githubusercontent.com/lehoangtienpham2395/sortation-center-layout/main/data/history/history_index.json?t=${t}`,
        { cache: 'no-store' }
      ));
      if (historyIndexRes?.ok) {
        const histIdx = await historyIndexRes.json();
        // Hỗ trợ cả 2 field name: 'dates' (build_history_index) và 'available_dates' (legacy)
        const allDates: string[] = histIdx?.dates ?? histIdx?.available_dates ?? [];
        historyDates = allDates.filter((d: string) => d <= todayOpDate);
      }
    } catch (_) { /* history index optional */ }

    const ibDatesFromRows = ibRows && ibRows.length > 0
      ? Array.from(new Set(
          (ibRows ?? []).map((r: any) => r['Ngày vận hành_Inbound'] || r['op_date_inbound'] || r['Ngày vận hành_Forecast'] || r['op_date_forecast'])
          .filter(Boolean)
        )).filter((d: any) => d <= todayOpDate) as string[]
      : [];

    // Merge: live ibDates rows + history index + todayOpDate
    const ibDatesAll = Array.from(new Set([
      todayOpDate,
      ...ibDatesFromRows,
      ...historyDates,
    ])).filter(d => d <= todayOpDate);
    ibDatesAll.sort((a, b) => b.localeCompare(a));

    // 📅 Lưu danh sách ngày riêng cho Inbound DatePicker (độc lập với Layout)
    setInboundAvailableDates(ibDatesAll);

    if (ibDatesAll.length > 0) {
      setSelectedInboundDate(prev => {
        // Lần đầu load (user chưa chọn tay) → luôn về todayOpDate (ngày vận hành)
        // todayOpDate tự tính: trước 06:00 = hôm qua, sau 06:00 = hôm nay
        if (!userChangedInboundDate.current) {
          return todayOpDate;
        }
        // User đã chủ động chọn ngày → giữ nguyên nếu còn hợp lệ
        if (prev && ibDatesAll.includes(prev)) return prev;
        // Nếu ngày cũ không còn trong list → về todayOpDate
        return ibDatesAll.includes(todayOpDate) ? todayOpDate : (ibDatesAll[0] ?? prev);
      });
    }

    const combined: SheetRow[] = [
      ...(outboundRows ?? []),
      ...(backlogRows  ?? []),
      ...(inventoryRows ?? []),
    ];

    setRawSheetRows(combined);

    // Extract unique dates from all sources (Outbound, Backlog, Inventory, Inbound, History Index)
    const dates = Array.from(new Set([
      todayOpDate,
      ...combined.map(r => r.date).filter(Boolean),
      ...(ibRows ?? []).map((r: any) => r['Ngày vận hành_Inbound'] || r['op_date_inbound'] || r['Ngày vận hành_Forecast'] || r['op_date_forecast']).filter(Boolean),
      ...historyDates,
    ])).filter(d => d <= todayOpDate) as string[];
    dates.sort((a, b) => b.localeCompare(a));
    const recentDates = dates.slice(0, 30); // Show up to 30 historical dates
    setAvailableDates(recentDates);

    if (recentDates.length > 0) {
      setSelectedDate(prev => {
        // 1. Giữ nguyên ngày người dùng đang chọn trên Layout
        if (prev && recentDates.includes(prev)) return prev;
        // 2. Lần đầu load mới mặc định lấy todayOpDate
        if (recentDates.includes(todayOpDate)) return todayOpDate;
        return recentDates[0];
      });
    }

    setLoading(false);
  };

  // 🎯 TỰ ĐỘNG RE-FETCH MICRO-JSON MỖI KHI NGƯỜI DÙNG ĐỔI NGÀY TRÊN DATEPICKER (Bỏ qua lần mount đầu đã được fetchAndUpdateData nạp sẵn)
  const isFirstMountRef = useRef(true);
  useEffect(() => {
    if (isFirstMountRef.current) {
      isFirstMountRef.current = false;
      return;
    }
    if (!selectedInboundDate) return;
    let isMounted = true;
    (async () => {
      try {
        const [kpiSummary, hourlyTrend, ordersStatus, truckEtaMicro, originStation] = await Promise.all([
          fetchMicroJson<any>('inbound_kpi_summary.json', selectedInboundDate),
          fetchMicroJson<any>('inbound_hourly_trend.json', selectedInboundDate),
          fetchMicroJson<any>('inbound_orders_status.json', selectedInboundDate),
          fetchMicroJson<any>('inbound_truck_eta.json', selectedInboundDate),
          fetchMicroJson<any>('inbound_origin_station.json', selectedInboundDate),
        ]);
        if (isMounted) {
          if (kpiSummary) setMicroKpiSummary(kpiSummary);
          if (hourlyTrend) setMicroHourlyTrend(hourlyTrend);
          if (ordersStatus) setMicroOrdersStatus(ordersStatus);
          if (truckEtaMicro) {
            setMicroTruckEta(truckEtaMicro);
            const trucks = truckEtaMicro?.trucks;
            if (Array.isArray(trucks) && trucks.length > 0) setTruckEtaData(trucks);
          }
          if (originStation) setMicroOriginStation(originStation);
        }
      } catch (microErr) {
        console.warn('Error refetching micro-JSON for selectedInboundDate:', selectedInboundDate, microErr);
      }
    })();
    return () => { isMounted = false; };
  }, [selectedInboundDate]);

  // Derived state/Filtering effect for Layout Racks & Control Center
  useEffect(() => {

    const normalizeDateStr = (dStr: string): string => {
      if (!dStr) return '';
      const str = String(dStr).trim();
      if (/^\d{4}-\d{2}-\d{2}/.test(str)) return str.slice(0, 10);
      const dt = new Date(str);
      if (!isNaN(dt.getTime())) {
        const yyyy = dt.getFullYear();
        const mm = String(dt.getMonth() + 1).padStart(2, '0');
        const dd = String(dt.getDate()).padStart(2, '0');
        return `${yyyy}-${mm}-${dd}`;
      }
      return str.slice(0, 10);
    };

    const isDateMatch = (rDate: string, sDate: string) => {
      if (!sDate) return true;
      if (!rDate) return false;
      const normR = normalizeDateStr(rDate);
      const normS = normalizeDateStr(sDate);
      if (sDate.includes('..')) {
        const [start, end] = sDate.split('..');
        return normR >= normalizeDateStr(start) && normR <= normalizeDateStr(end);
      }
      return normR === normS;
    };

    // 🎯 KHÔNG TỰ Ý FALLBACK SANG NGÀY CŨ KHI MỘT NGÀY CHƯA CÓ ĐƠN (Ví dụ Ngày 01/08 chưa có đơn Outbound -> Giữ nguyên 0 đơn)
    const effectiveDate = selectedDate || (availableDates[0] || '');

    // Create lookup maps for selectedType, backlog, and inventory per areaId
    const selectedMap: Record<string, { volume: number; weight: number; capacity: number; buuCuc: string }> = {};
    const backlogMap: Record<string, { volume: number; weight: number; capacity: number; buuCuc: string }> = {};
    const inventoryMap: Record<string, { volume: number; weight: number; capacity: number; buuCuc: string }> = {};

    rawSheetRows.forEach(row => {
      const key = row.areaId;
      if (!key) return;

      const rowStatus = row.status ? String(row.status) : '';

      // 🎯 BỘ LỌC TRẠNG THÁI (Inbound, Transporting, Pickup Done, Created, Outbound)
      const statusMatched = !rowStatus || selectedStatuses.includes(rowStatus);

      // 🎯 BỘ LỌC NGÀY VẬN HÀNH — chỉ áp dụng cho Outbound
      // Backlog = số LIVE (không lọc ngày) — hàng inbound nhưng chưa outbound TẤT CẢ ngày
      // Volume  = số LIVE (không lọc ngày) — tất cả đơn chưa xuất kho TẤT CẢ ngày
      const isOutboundMode  = selectedType === 'Outbound';
      const isBacklogMode   = selectedType === 'Backlog';
      const isVolumeMode    = selectedType === 'Inventory' || selectedType === 'Volume';

      // 🎯 BỘ LỌC NGÀY VẬN HÀNH:
      // Outbound & Inventory: Lọc theo ngày vận hành được chọn (effectiveDate)
      // Giúp ngăn ngừa lặp đúp dữ liệu lịch sử các ngày cũ trong inventory.json
      if (isOutboundMode || row.type === 'Inventory') {
        const dateMatched = !effectiveDate || isDateMatch(row.date, effectiveDate);
        if (!dateMatched) return;
      }

      // 🎯 BỘ LỌC LOẠI (Outbound / Backlog / Volume)
      let isForSelectedType = false;
      if (isOutboundMode) {
        isForSelectedType = row.type === 'Outbound' || rowStatus === 'Outbound';
      } else if (isBacklogMode) {
        isForSelectedType = row.type === 'Backlog' && statusMatched;
      } else if (isVolumeMode) {
        isForSelectedType = (row.type === 'Inventory' || row.type === 'Backlog') && rowStatus !== 'Outbound' && statusMatched;
      }

      if (isForSelectedType) {
        if (!selectedMap[key]) {
          const defaultCap = key === 'A06' ? 1400 : 780;
          selectedMap[key] = { volume: 0, weight: 0, capacity: (row.capacity && row.capacity > 0 && key !== 'A06') ? row.capacity : defaultCap, buuCuc: row.buuCuc };
        }
        selectedMap[key].volume += row.volume;
        selectedMap[key].weight += row.weight;
      }

      // Populate inventoryMap (dùng cho tooltip — không filter ngày)
      if (row.type === 'Inventory' && statusMatched) {
        if (!inventoryMap[key]) {
          inventoryMap[key] = { volume: 0, weight: 0, capacity: row.capacity || 780, buuCuc: row.buuCuc };
        }
        inventoryMap[key].volume += row.volume;
        inventoryMap[key].weight += row.weight;
      }

      // Populate backlogMap LIVE — Inbound chưa Outbound, TẤT CẢ ngày (không filter ngày)
      // Chỉ từ backlog.json (type=Backlog) — has_in=True AND has_out=False
      if (row.type === 'Backlog' && rowStatus !== 'Outbound') {
        if (!backlogMap[key]) {
          backlogMap[key] = { volume: 0, weight: 0, capacity: row.capacity || 780, buuCuc: row.buuCuc };
        }
        backlogMap[key].volume += row.volume;
        backlogMap[key].weight += row.weight;
      }
    });

    // Update static lists
    const updateListName = (list: any[]) => {
      list.forEach(item => {
        const key = item.areaId;
        const invEntry = inventoryMap[key];
        const activeItem = selectedMap[key] || backlogMap[key];
        
        const name = MASTER_CONFIG_MAP[key] || invEntry?.buuCuc || activeItem?.buuCuc;
        if (name && name !== 'Chờ tải' && !name.includes('Dự phòng')) {
          item.name = name;
        } else if (item.name && !item.name.includes('Dự phòng')) {
          // Keep whatever is already statically set in ZONE arrays
        } else {
          item.name = item.areaId + " Dự phòng";
        }
      });
    };
    updateListName(ZONE3_LIST);
    updateListName(ZONE2_LIST);
    updateListName(ZONE1_LIST);

    const totalOrdersOfSelectedType = Object.values(selectedMap).reduce((sum, item) => sum + item.volume, 0);
    const totalWeightOfSelectedType = Object.values(selectedMap).reduce((sum, item) => sum + item.weight, 0);
    setTotalOrders(totalOrdersOfSelectedType);
    setTotalWeight(totalWeightOfSelectedType);

    // Recompute visual data for ALL_RACKS
    const newData = ALL_RACKS.reduce((acc, curr: any) => {
      let capacity = 780;
      let current = 0;
      let weight = 0;
      let util = 0;
      let backlogCurrent = 0;

      const key = curr.areaId || null;

      if (key) {
        const item = selectedMap[key];
        const blItem = backlogMap[key];

        if (item) {
          capacity = item.capacity || 780;
          current = item.volume;
          weight = item.weight || 0;
        }

        if (blItem && blItem.volume !== -1) {
          backlogCurrent = blItem.volume;
          if (selectedType === 'Backlog') {
            capacity = blItem.capacity || 780;
            current = blItem.volume;
            weight = blItem.weight || 0;
          }
        }

        // Calculate utilization based on capacity for all modes (Standard current / capacity * 100)
        util = capacity > 0 ? Math.floor((current / capacity) * 100) : 0;
      }

      if (curr.areaId === 'A06') {
        capacity = 1400;
        util = capacity > 0 ? Math.floor((current / capacity) * 100) : 0;
      }

      let bucket = 'green';
      if (util > 100) bucket = 'darkred';
      else if (util >= 95) bucket = 'red';
      else if (util >= 80) bucket = 'orange';
      else if (util >= 50) bucket = 'yellow';

      acc[curr.areaId] = {
        current,
        backlogCurrent,
        weight,
        capacity,
        remaining: Math.max(0, capacity - current),
        utilization: util,
        bucket,
        name: curr.name
      };
      return acc;
    }, {} as any);

    setData(newData);
  }, [rawSheetRows, selectedDate, selectedType, selectedStatuses]);

  const getZoneInfo = (zone: number) => {
    let activeChutesCount = 0;
    let zoneOrders = 0;
    let zoneWeight = 0;
    const zoneChutes = CHUTE_RACKS.filter(c => c.zone === zone);
    
    zoneChutes.forEach(c => {
      const d = data[c.areaId];
      if (d) {
        zoneOrders += d.current;
        zoneWeight += d.weight ?? 0;
        if (d.current > 0) {
          activeChutesCount++;
        }
      }
    });

    const ratio = totalOrders > 0 ? ((zoneOrders / totalOrders) * 100).toFixed(1) : '0.0';

    return {
      zone,
      activeChutesCount,
      totalChutes: zoneChutes.length,
      zoneOrders,
      zoneWeight,
      ratio
    };
  };

  const getTop10Chutes = () => {
    return CHUTE_RACKS.map(c => {
      const d = data[c.areaId] || { current: 0, weight: 0, capacity: 780, utilization: 0, bucket: 'green', name: c.name };
      return {
        areaId: c.areaId,
        name: d.name || c.name,
        current: d.current,
        weight: d.weight || 0,
        utilization: d.utilization,
        bucket: d.bucket,
        zone: c.zone
      };
    })
    .sort((a, b) => b.current - a.current)
    .slice(0, 10);
  };

  const [scale, setScale] = useState(1);
  const [translateX, setTranslateX] = useState(0);
  const [translateY, setTranslateY] = useState(0);
  const [isDragging, setIsDragging] = useState(false);
  const [dragStart, setDragStart] = useState({ x: 0, y: 0 });

  const handleWheel = (e: React.WheelEvent<SVGSVGElement>) => {
    const zoomFactor = 1.08;
    let newScale = scale;
    if (e.deltaY < 0) {
      newScale = Math.min(scale * zoomFactor, 6);
    } else {
      newScale = Math.max(scale / zoomFactor, 0.5);
    }
    setScale(newScale);
  };

  const handleMouseDown = (e: React.MouseEvent<SVGSVGElement>) => {
    if (e.button !== 0) return; // Left click drag only
    setIsDragging(true);
    setDragStart({ x: e.clientX - translateX, y: e.clientY - translateY });
  };

  const handleMouseMove = (e: React.MouseEvent<SVGSVGElement>) => {
    if (!isDragging) return;
    setTranslateX(e.clientX - dragStart.x);
    setTranslateY(e.clientY - dragStart.y);
  };

  const handleMouseUp = () => {
    setIsDragging(false);
  };

  const handleResetZoom = () => {
    setScale(1);
    setTranslateX(0);
    setTranslateY(0);
  };

  const handleZoomIn = () => {
    setScale(prev => Math.min(prev * 1.2, 6));
  };
  const handleZoomOut = () => {
    setScale(prev => Math.max(prev / 1.2, 0.5));
  };

  const handleTouchStart = (e: React.TouchEvent<SVGSVGElement>) => {
    if (e.touches.length !== 1) return;
    setIsDragging(true);
    const touch = e.touches[0];
    setDragStart({ x: touch.clientX - translateX, y: touch.clientY - translateY });
  };

  const handleTouchMove = (e: React.TouchEvent<SVGSVGElement>) => {
    if (!isDragging || e.touches.length !== 1) return;
    const touch = e.touches[0];
    setTranslateX(touch.clientX - dragStart.x);
    setTranslateY(touch.clientY - dragStart.y);
  };

  const handleTouchEnd = () => {
    setIsDragging(false);
  };

  const handleGoogleBtnMouseMove = (e: React.MouseEvent<HTMLButtonElement>) => {
    const rect = e.currentTarget.getBoundingClientRect();
    const x = e.clientX - rect.left;
    const y = e.clientY - rect.top;
    e.currentTarget.style.setProperty('--mouse-x', `${x}px`);
    e.currentTarget.style.setProperty('--mouse-y', `${y}px`);
  };

  const lastUpdateTimestampRef = useRef<string | null>(null);

  useEffect(() => {
    const BUILD_VER = '20260801_1022_PURGE_CACHE_V5';
    if (localStorage.getItem('app_build_ver') !== BUILD_VER) {
      localStorage.setItem('app_build_ver', BUILD_VER);
      window.location.reload();
      return;
    }

    let intervalId: any = null;

    const initDataAndPoll = async () => {
      // 1. Initial single-pass fetch (sequential await)
      await fetchAndUpdateData();

      // 2. ONLY AFTER initial fetch completes, define and start background polling
      const checkAndPoll = async () => {
        try {
          const t = `${Date.now()}_${Math.floor(Math.random() * 100000)}`;
          const fetchOpts: RequestInit = {
            cache: 'no-store',
            headers: {
              'Cache-Control': 'no-cache, no-store, must-revalidate',
              'Pragma': 'no-cache'
            }
          };
          const baseUrl = getApiUrl('last_update.json');
          const cacheBustUrl = baseUrl.includes('?') ? `${baseUrl}&t=${t}` : `${baseUrl}?t=${t}`;
          let res = await fetch(cacheBustUrl, fetchOpts);
          if (!res.ok && getApiUrl('').startsWith('./')) {
            res = await fetch(`https://raw.githubusercontent.com/lehoangtienpham2395/sortation-center-layout/main/data/last_update.json?t=${t}`, fetchOpts);
          }
          if (res.ok) {
            const d = await res.json();
            const newTime = d?.last_update || null;
            if (lastUpdateTimestampRef.current && newTime && newTime !== lastUpdateTimestampRef.current) {
              console.log(`[Auto Sync] Dữ liệu mới phát hiện (${lastUpdateTimestampRef.current} -> ${newTime}). Đang tự động cập nhật...`);
              lastUpdateTimestampRef.current = newTime;
              await fetchAndUpdateData();
            }
          }
        } catch (e) {
          console.error('[Auto Sync] Lỗi kiểm tra last_update:', e);
        }
      };

      intervalId = setInterval(checkAndPoll, 5000);
    };

    initDataAndPoll();

    const handleResize = () => {
      setIsMobile(window.innerWidth < 768);
    };
    window.addEventListener('resize', handleResize);

    return () => {
      window.removeEventListener('resize', handleResize);
      if (intervalId) clearInterval(intervalId);
    };
  }, []);

  useEffect(() => {
    if (currentView === 'inbound') {
      const rawTrucksList: any[] = (() => {
        if (microTruckEta?.trucks && microTruckEta.trucks.length > 0) return microTruckEta.trucks;
        if (Array.isArray(truckEtaData) && truckEtaData.length > 0) return truckEtaData;
        return (truckEtaData as any)?.trucks || [];
      })();

      const activeDate = selectedInboundDate || getTodayOpDate();
      const filteredTrucks = rawTrucksList.filter((d: any) => {
        const opD = d.op_date || (d.eta || d.planned_arrival || '').slice(0, 10);
        return !opD || isDateMatch(opD, activeDate);
      });

      const stationMap: Record<string, number> = {};
      filteredTrucks.forEach(d => {
        const station = (d.send_network || d.sendNetworkName || d['Bưu cục đi'] || d.Pickup_station || d.station || '').trim().toUpperCase();
        if (!station) return;
        const orders = Number(d.orders_count ?? d.volume ?? d['Tổng số đơn'] ?? 0);
        if (orders > 0) {
          stationMap[station] = (stationMap[station] || 0) + orders;
        }
      });

      const sortedStations = Object.entries(stationMap)
        .sort((a, b) => b[1] - a[1])
        .slice(0, 5);

      if (sortedStations.length > 0) {
        const totalVehicles = filteredTrucks.length;
        const totalOrdersCount = filteredTrucks.reduce((sum, d) => sum + Number(d.orders_count ?? d.volume ?? d['Tổng số đơn'] ?? 0), 0);
        const warningItems = sortedStations.map(([st, vol]) => `${st} (${vol.toLocaleString()} đơn)`);
        const warningText = `DANH SÁCH ${totalVehicles} XE VÀ ${totalOrdersCount.toLocaleString()} ĐƠN ĐANG ĐẾN HUB — TOP BƯU CỤC CÓ SẢN LƯỢNG CAO NHẤT: ` + warningItems.join(' // ');
        setTickerText(warningText);
      } else {
        setTickerText(`HỆ THỐNG INBOUND ỔN ĐỊNH — KHÔNG CÓ XE ĐANG VỀ`);
      }
    } else {
      let tCap=0, tCur=0, tRem=0, tOver=0, tUsed=0, tBacklog=0, tWeight=0;
      const alerts: string[] = [];
      CHUTE_RACKS.forEach(c => {
        const d = data[c.areaId]; if (!d) return;
        tCap += d.capacity; tCur += d.current; tRem += d.remaining;
        tBacklog += d.backlogCurrent ?? 0;
        tWeight += d.weight ?? 0;
        if (d.current > 0) tUsed++;
        if (d.utilization > 100) { tOver++; alerts.push(`${c.areaId} VƯỢT SỨC CHỨA (${d.utilization}%)`); }
        else if (d.utilization >= 95) alerts.push(`${c.areaId} SẮP ĐẦY (${d.utilization}%)`);
      });
      
      // Always compute outbound rate regardless of selectedType
      const outDenominator = tCur + tBacklog;
      setOutboundRate((outDenominator ? (tCur / outDenominator) * 100 : 0).toFixed(1));

      // TỈ LỆ LẤP ĐẦY card always computes Capacity Fill Rate (tCur / tCap) * 100
      setUtilTotal((tCap ? (tCur / tCap) * 100 : 0).toFixed(1));
      
      setFree(tRem); setUsedCells(tUsed); setTotalOrders(tCur); setTotalWeight(tWeight);
      
      const label = selectedType === 'Outbound' ? 'TỈ LỆ OUTBOUND' : 'LẤP ĐẦY';
      const rate = selectedType === 'Outbound'
        ? (tCur + tBacklog ? (tCur / (tCur + tBacklog)) * 100 : 0)
        : (tCap ? (tCur / tCap) * 100 : 0);
        
      setTickerText(alerts.length > 0
        ? alerts.join(' // ') + ' // ' + alerts.join(' // ')
        : `HỆ THỐNG ỔN ĐỊNH — KHÔNG CÓ CẢNH BÁO // TỔNG ${tCur} ĐƠN HÀNG // ${label} ${rate.toFixed(1)}%`
      );
    }
  }, [currentView, data, selectedType, arrivalData, inboundData, selectedInboundDate]);

  const getZoneBorderProps = (zone: number, colorVar: string) => {
    const isHovered = hoveredZone === zone;
    return {
      fill: 'none',
      stroke: `var(${colorVar})`,
      strokeWidth: isHovered ? 1.5 : 0.8,
      strokeOpacity: isHovered ? 1.0 : 0.5,
      style: {
        transition: 'all 0.3s cubic-bezier(0.4, 0, 0.2, 1)',
        filter: isHovered 
          ? `drop-shadow(0 3px 6px rgba(0,0,0,0.4)) drop-shadow(0 3px 6px var(${colorVar}))` 
          : 'none'
      },
      pointerEvents: 'none' as const
    };
  };

  const renderSVG = () => {
    return (
      <svg viewBox="0 0 1100 660" className="w-full h-full max-h-[75vh] md:max-h-[85vh] drop-shadow-2xl select-none"
             onWheel={handleWheel}
             onMouseDown={handleMouseDown}
             onMouseMove={handleMouseMove}
             onMouseUp={handleMouseUp}
             onMouseLeave={handleMouseUp}
             onTouchStart={handleTouchStart}
             onTouchMove={handleTouchMove}
             onTouchEnd={handleTouchEnd}
             style={{ cursor: isDragging ? 'grabbing' : 'grab' }}>
          <defs>
            <pattern id="mesh" width="10" height="10" patternUnits="userSpaceOnUse">
              <path d="M10 0H0V10" fill="none" stroke="rgba(255,255,255,.04)" strokeWidth="0.7"/>
            </pattern>
            <pattern id="dock-stripe" width="10" height="10" patternUnits="userSpaceOnUse" patternTransform="rotate(45)">
              <rect width="10" height="10" fill="transparent"/>
              <line x1="0" y1="0" x2="0" y2="10" stroke="rgba(234,179,8,.22)" strokeWidth="3"/>
            </pattern>
            <pattern id="path-stripe" width="12" height="12" patternUnits="userSpaceOnUse" patternTransform="rotate(45)">
              <rect width="12" height="12" fill="transparent"/>
              <line x1="0" y1="0" x2="0" y2="12" stroke="rgba(234,179,8,.14)" strokeWidth="5"/>
            </pattern>
            <marker id="arrow" viewBox="0 0 10 10" refX="7" refY="5" markerWidth="6" markerHeight="6" orient="auto">
              <path d="M 2 2.5 L 7.5 5 L 2 7.5 z" fill="rgba(234,179,8,0.85)"/>
            </marker>
            <marker id="arrow-blue" viewBox="0 0 10 10" refX="7" refY="5" markerWidth="6" markerHeight="6" orient="auto">
              <path d="M 2 2.5 L 7.5 5 L 2 7.5 z" fill="rgba(96,165,250,0.85)"/>
            </marker>
          </defs>
          <g transform={`translate(${translateX}, ${translateY}) scale(${scale})`} style={{ transformOrigin: '550px 330px' }}>

          <rect x={WL} y={WT} width={WR-WL} height={WB-WT}
                rx="5" fill="#0c111e" fillOpacity="0.45" stroke="#1f2d4d" strokeWidth="2"/>
          <rect x={WL} y={WT} width={WR-WL} height={WB-WT}
                rx="5" fill="url(#mesh)" pointerEvents="none"/>

          <line x1={A12_X} y1={WT} x2={A12_X} y2={WB}
                stroke="#1c2d4a" strokeWidth="1.5" strokeDasharray="6 5"/>
          <line x1={A23_X} y1={WT}  x2={A23_X} y2={72} stroke="#8da0c4" strokeWidth="3"/>
          <line x1={A23_X} y1={118} x2={A23_X} y2={230} stroke="#8da0c4" strokeWidth="3"/>
          <line x1={A23_X} y1={280} x2={A23_X} y2={392} stroke="#8da0c4" strokeWidth="3"/>
          <line x1={A23_X} y1={452} x2={A23_X} y2={WB}  stroke="#8da0c4" strokeWidth="3"/>


          <text x={(WL+A12_X)/2} y={WT-8} textAnchor="middle"
                fill="#8da0c4" className="disp text-[11px] font-extrabold tracking-wider">A1 (47.2M)</text>
          <text x={(A12_X+A23_X)/2} y={WT-8} textAnchor="middle"
                fill="#8da0c4" className="disp text-[11px] font-extrabold tracking-wider">A2 (36M)</text>
          <text x={(A23_X+WR)/2} y={WT-8} textAnchor="middle"
                fill="#8da0c4" className="disp text-[11px] font-extrabold tracking-wider">A3 (36M)</text>

          <rect x={NS_X} y={PASS1_Y} width={NS_W} height={WB-PASS1_Y}
                fill="url(#path-stripe)" stroke="rgba(234,179,8,0.3)" strokeWidth="1"/>
          <line x1={NS_X+NS_W/2} y1={PASS1_Y+4} x2={NS_X+NS_W/2} y2={WB-4}
                stroke="rgba(234,179,8,0.2)" strokeWidth="1" strokeDasharray="8 6"/>
          <text x={NS_X+NS_W/2} y={(PASS1_Y+WB)/2} textAnchor="middle"
                fill="rgba(234,179,8,0.55)" className="mono text-[6.5px] font-bold tracking-wider"
                transform={`rotate(-90 ${NS_X+NS_W/2} ${(PASS1_Y+WB)/2})`}
                pointerEvents="none">ĐƯỜNG ĐI DỌC (5M) — TỪ CỔNG A18</text>

          <rect x={Z_L} y={PASS1_Y} width={NS_X-Z_L} height={PASS1_H}
                fill="url(#path-stripe)" stroke="rgba(234,179,8,0.25)" strokeWidth="0.8"/>
          <line x1={Z_L+4} y1={PASS1_Y+PASS1_H/2} x2={NS_X-4} y2={PASS1_Y+PASS1_H/2}
                stroke="rgba(234,179,8,0.2)" strokeWidth="1" strokeDasharray="10 7"/>
          <text x={(Z_L+NS_X)/2} y={PASS1_Y+PASS1_H/2+3} textAnchor="middle"
                fill="rgba(234,179,8,0.5)" className="mono text-[6.5px] font-bold tracking-wider"
                pointerEvents="none">ĐƯỜNG NGANG TRÊN (6M)</text>

          <rect x={Z_L} y={EW_Y} width={NS_X-Z_L} height={EW_H}
                fill="url(#path-stripe)" stroke="rgba(234,179,8,0.25)" strokeWidth="0.8"/>
          <line x1={Z_L+4} y1={EW_Y+EW_H/2} x2={NS_X-4} y2={EW_Y+EW_H/2}
                stroke="rgba(234,179,8,0.2)" strokeWidth="1" strokeDasharray="10 7"/>
          <text x={(Z_L+NS_X)/2} y={EW_Y+EW_H/2+3} textAnchor="middle"
                fill="rgba(234,179,8,0.5)" className="mono text-[6.5px] font-bold tracking-wider"
                pointerEvents="none">ĐƯỜNG NGANG GIỮA (6M)</text>



          <rect x={Z1_L} y={EW2_Y} width={NS_X-Z1_L} height={EW2_H}
                fill="url(#path-stripe)" stroke="rgba(234,179,8,0.25)" strokeWidth="0.8"/>
          <line x1={Z1_L+4} y1={EW2_Y+EW2_H/2} x2={NS_X-4} y2={EW2_Y+EW2_H/2}
                stroke="rgba(234,179,8,0.2)" strokeWidth="1" strokeDasharray="10 7"/>
          <text x={(Z1_L+NS_X)/2} y={EW2_Y+EW2_H/2+3} textAnchor="middle"
                fill="rgba(234,179,8,0.5)" className="mono text-[6.5px] font-bold tracking-wider"
                pointerEvents="none">ĐƯỜNG NGANG DƯỚI (6M)</text>

          <line x1={NS_X+NS_W/2} y1={WB-15} x2={NS_X+NS_W/2} y2={PASS1_Y+PASS1_H/2}
                fill="none" stroke="rgba(234,179,8,0.45)" strokeWidth="1.2" strokeDasharray="4 3"/>
          <line x1={NS_X+NS_W/2} y1={PASS1_Y+PASS1_H/2} x2={Z_R-20} y2={PASS1_Y+PASS1_H/2}
                fill="none" stroke="rgba(234,179,8,0.55)" strokeWidth="1.5" markerEnd="url(#arrow)"/>
          <line x1={NS_X+NS_W/2} y1={EW_Y+EW_H/2} x2={Z_R-20} y2={EW_Y+EW_H/2}
                fill="none" stroke="rgba(234,179,8,0.55)" strokeWidth="1.5" markerEnd="url(#arrow)"/>
          <line x1={NS_X+NS_W/2} y1={EW2_Y+EW2_H/2} x2={Z_R-20} y2={EW2_Y+EW2_H/2}
                fill="none" stroke="rgba(234,179,8,0.55)" strokeWidth="1.5" markerEnd="url(#arrow)"/>

          <text x={NS_X+NS_W/2-24} y={PASS1_Y+PASS1_H+8} fill="rgba(234,179,8,0.75)" className="mono text-[5.5px] font-bold">RẼ TRÁI (LỐI 1)</text>
          <text x={NS_X+NS_W/2-24} y={EW_Y+EW_H+8} fill="rgba(234,179,8,0.75)" className="mono text-[5.5px] font-bold">RẼ TRÁI (LỐI 2)</text>
          <text x={NS_X+NS_W/2-24} y={EW2_Y+EW2_H+8} fill="rgba(234,179,8,0.75)" className="mono text-[5.5px] font-bold">RẼ TRÁI (LỐI 3)</text>

          <g>
            {/* Zone 3 Chutes */}
            {ZONE3_LIST.filter(c => c.areaId !== 'C26').map((c, i) => {
              const d = data[c.areaId]; if (!d) return null;
              const isRight = i < 5;
              const bx = isRight ? 642 + (4 - i) * TR_BAY_W : 614 - (i - 5) * TR_BAY_W;
              const by = Z3_Y;
              return (
                <ZoneCell key={c.areaId} c={c} d={d} bx={bx} by={by}
                          bw={TR_BAY_W} bh={Z_H} midLabelY={by+Z_H/2}
                          isHovered={hoveredRack?.areaId===c.areaId}
                          onEnter={() => {
                            setHoveredRack({...c,...d});
                            if (c.zone) setHoveredZone(c.zone);
                          }}
                          onLeave={() => {
                            setHoveredRack(null);
                            setHoveredZone(null);
                          }}
                          onClick={() => {
                            setHoveredRack({...c,...d});
                            setSelectedDetailRack({ item: c, detail: d });
                          }}
                          addCenterLine={true}/>
              );
            })}
            {/* Zone 3 Trucks (Song song phía dưới Zone 3) */}
            {ZONE3_TRUCKS.map((c, i) => {
              const d = data[c.areaId]; if (!d) return null;
              const bx = 754 - i * TR_BAY_W;
              const by = 174;
              return (
                <g key={c.areaId}>
                  <ZoneCell c={c} d={d} bx={bx} by={by}
                            bw={TR_BAY_W} bh={Z_H} midLabelY={by+Z_H/2}
                            isHovered={hoveredRack?.areaId===c.areaId}
                            onEnter={() => {
                              setHoveredRack({...c,...d});
                              if (c.zone) setHoveredZone(c.zone);
                            }}
                            onLeave={() => {
                              setHoveredRack(null);
                              setHoveredZone(null);
                            }}
                            onClick={() => {
                              setHoveredRack({...c,...d});
                              if (isMobile) setBottomSheetOpen(true);
                            }}
                            isTruck={true}/>
                  <g pointerEvents="none" opacity="0.8">
                    <rect x={bx+4} y={by+4} width={TR_BAY_W-8} height={Z_H-22}
                          rx="1" fill="rgba(255,255,255,0.15)" stroke="rgba(255,255,255,0.4)" strokeWidth="0.6"/>
                    <rect x={bx+3} y={by+Z_H-16} width={TR_BAY_W-6} height={10}
                          rx="1.5" fill="rgba(255,255,255,0.25)" stroke="rgba(255,255,255,0.5)" strokeWidth="0.7"/>
                  </g>
                </g>
              );
            })}
            {/* Zone 3 Chutes Left border (bao quanh C06->C25) */}
            <rect x={82} y={118} width={560} height={Z_H} rx="2"
                  {...getZoneBorderProps(3, '--green')}/>
            {/* Zone 3 Chutes Right border (bao quanh C01->C05) */}
            <rect x={642} y={118} width={140} height={Z_H} rx="2"
                  {...getZoneBorderProps(3, '--green')}/>
            {/* Zone 3 Trucks border (bao quanh T3-01->T3-24) */}
            <rect x={110} y={174} width={672} height={Z_H} rx="2"
                  {...getZoneBorderProps(3, '--green')}/>
          </g>

          <g>
            {/* Zone 2 Chutes */}
            {ZONE2_LIST.map((c, i) => {
              const d = data[c.areaId]; if (!d) return null;
              const isRight = i < 5;
              const bx = isRight ? 642 + (4 - i) * TR_BAY_W : 614 - (i - 5) * TR_BAY_W;
              const by = Z2_Y;
              return (
                <ZoneCell key={c.areaId} c={c} d={d} bx={bx} by={by}
                          bw={TR_BAY_W} bh={Z_H} midLabelY={by+Z_H/2}
                          isHovered={hoveredRack?.areaId===c.areaId}
                          onEnter={() => {
                            setHoveredRack({...c,...d});
                            if (c.zone) setHoveredZone(c.zone);
                          }}
                          onLeave={() => {
                            setHoveredRack(null);
                            setHoveredZone(null);
                          }}
                          addCenterLine={true}/>
              );
            })}
            {/* Zone 2 Trucks (Song song phía trên Zone 2) */}
            {ZONE2_TRUCKS.map((c, i) => {
              const d = data[c.areaId]; if (!d) return null;
              const bx = 754 - i * TR_BAY_W;
              const by = 280;
              return (
                <g key={c.areaId}>
                  <ZoneCell c={c} d={d} bx={bx} by={by}
                            bw={TR_BAY_W} bh={Z_H} midLabelY={by+Z_H/2}
                            isHovered={hoveredRack?.areaId===c.areaId}
                            onEnter={() => {
                              setHoveredRack({...c,...d});
                              if (c.zone) setHoveredZone(c.zone);
                            }}
                            onLeave={() => {
                              setHoveredRack(null);
                              setHoveredZone(null);
                            }}
                            onClick={() => {
                              setHoveredRack({...c,...d});
                              if (isMobile) setBottomSheetOpen(true);
                            }}
                            isTruck={true}/>
                  <g pointerEvents="none" opacity="0.8">
                    <rect x={bx+3} y={by+6} width={TR_BAY_W-6} height={10}
                          rx="1.5" fill="rgba(255,255,255,0.25)" stroke="rgba(255,255,255,0.5)" strokeWidth="0.7"/>
                    <rect x={bx+4} y={by+18} width={TR_BAY_W-8} height={Z_H-22}
                          rx="1" fill="rgba(255,255,255,0.15)" stroke="rgba(255,255,255,0.4)" strokeWidth="0.6"/>
                  </g>
                </g>
              );
            })}
            {/* Zone 2 Chutes Left border (bao quanh B01->B16, đã bỏ B17-B18) */}
            <rect x={194} y={336} width={448} height={Z_H} rx="2"
                  {...getZoneBorderProps(2, '--yellow')}/>
            {/* Zone 2 Chutes Right border (bao quanh A00->A04, now Zone 3) */}
            <rect x={642} y={336} width={140} height={Z_H} rx="2"
                  {...getZoneBorderProps(3, '--green')}/>
            {/* Zone 2 Trucks border (bao quanh T2-01->T2-16) */}
            <rect x={194} y={280} width={448} height={Z_H} rx="2"
                  {...getZoneBorderProps(2, '--yellow')}/>
            {/* Zone 3 Trucks border extension (bao quanh T2-17->T2-21) */}
            <rect x={642} y={280} width={140} height={Z_H} rx="2"
                  {...getZoneBorderProps(3, '--green')}/>
          </g>

          <line x1={(A23_X + NS_X)/2} y1={EW_Y+EW_H/2} x2={(A23_X + NS_X)/2} y2={EW_Y+3}
                fill="none" stroke="rgba(234,179,8,0.45)" strokeWidth="1.2" markerEnd="url(#arrow)"/>
          <line x1={(A23_X + NS_X)/2} y1={EW_Y+EW_H/2} x2={(A23_X + NS_X)/2} y2={EW_Y+EW_H-3}
                fill="none" stroke="rgba(234,179,8,0.45)" strokeWidth="1.2" markerEnd="url(#arrow)"/>
          <text x={(A23_X + NS_X)/2 + 20} y={EW_Y+EW_H/2+2} textAnchor="middle"
                fill="rgba(234,179,8,0.65)" className="mono text-[5.5px] font-bold">XE TẢI CHỤM ĐẦU</text>

          <g>
            {ZONE1_LIST.filter(c => c.areaId !== 'A06').map((c, i) => {
              const d = data[c.areaId]; if (!d) return null;
              const bx = 556 - i * TR_BAY_W;
              return <ZoneCell key={c.areaId} c={c} d={d} bx={bx} by={Z1_Y}
                               bw={TR_BAY_W} bh={Z_H} midLabelY={Z1_Y+Z_H/2}
                               isHovered={hoveredRack?.areaId===c.areaId}
                               onEnter={() => {
                                 setHoveredRack({...c,...d});
                                 if (c.zone) setHoveredZone(c.zone);
                               }}
                               onLeave={() => {
                                 setHoveredRack(null);
                                 setHoveredZone(null);
                               }}
                               onClick={() => {
                                 setHoveredRack({...c,...d});
                                 if (isMobile) setBottomSheetOpen(true);
                               }}
                               addCenterLine={true}/>;
            })}
            <rect x={192} y={Z1_Y} width={448} height={Z_H} rx="2"
                  {...getZoneBorderProps(1, '--orange')}/>

          </g>
 
          {/* Render C26 (Zone 3) separately next to BN HUB on the left */}
          <g>
            {(() => {
              const c = ZONE3_LIST.find(item => item.areaId === 'C26');
              if (!c) return null;
              const d = data[c.areaId];
              if (!d) return null;
              const bx = 153;
              const by = Z1_Y;
              const bw = TR_BAY_W;
              const isChuteHovered = hoveredRack?.areaId === 'C26';
              return (
                <>
                  <ZoneCell c={c} d={d} bx={bx} by={by}
                            bw={bw} bh={Z_H} midLabelY={by+Z_H/2}
                            isHovered={hoveredRack?.areaId===c.areaId}
                            onEnter={() => {
                              setHoveredRack({...c,...d});
                              setHoveredZone(3);
                            }}
                            onLeave={() => {
                              setHoveredRack(null);
                              setHoveredZone(null);
                            }}
                            onClick={() => {
                              setHoveredRack({...c,...d});
                              if (isMobile) setBottomSheetOpen(true);
                            }}
                            addCenterLine={true}/>
                  <rect x={bx} y={by} width={bw} height={Z_H} rx="2"
                        fill="none"
                        stroke="var(--green)"
                        strokeWidth={isChuteHovered ? 1.5 : 0.8}
                        strokeOpacity={isChuteHovered ? 1.0 : 0.5}
                        style={{
                          transition: 'all 0.3s cubic-bezier(0.4, 0, 0.2, 1)',
                          filter: isChuteHovered ? 'drop-shadow(0 3px 6px rgba(0,0,0,0.4)) drop-shadow(0 3px 6px var(--green))' : 'none'
                        }}
                        pointerEvents="none"/>
                </>
              );
            })()}
          </g>

          {/* Render A06 (BN HUB) separately next to A07 with double cell width */}
          <g>
            {(() => {
              const c = ZONE1_LIST.find(item => item.areaId === 'A06');
              if (!c) return null;
              const d = data[c.areaId];
              if (!d) return null;
              const bx = 584;
              const by = Z1_Y;
              const bw = 56; // 2 cells wide
              const isHubHovered = hoveredRack?.areaId === 'A06';
              return (
                <>
                  <ZoneCell c={c} d={d} bx={bx} by={by}
                            bw={bw} bh={Z_H} midLabelY={by+Z_H/2}
                            isHovered={hoveredRack?.areaId===c.areaId}
                            onEnter={() => {
                              setHoveredRack({...c,...d});
                              setHoveredZone(1);
                            }}
                            onLeave={() => {
                              setHoveredRack(null);
                              setHoveredZone(null);
                            }}
                            addCenterLine={true}/>
                  <rect x={bx} y={by} width={bw} height={Z_H} rx="2"
                        fill="none"
                        stroke="var(--orange)"
                        strokeWidth={isHubHovered ? 1.5 : 0.8}
                        strokeOpacity={isHubHovered ? 1.0 : 0.5}
                        style={{
                          transition: 'all 0.3s cubic-bezier(0.4, 0, 0.2, 1)',
                          filter: isHubHovered ? 'drop-shadow(0 3px 6px rgba(0,0,0,0.4)) drop-shadow(0 3px 6px var(--orange))' : 'none'
                        }}
                        pointerEvents="none"/>

                </>
              );
            })()}
          </g>
 
          {/* Zone 1 Trucks (Song song ngoài mặt DOCK, đối diện các ô Zone 1) */}
          <g>
            {ZONE1_TRUCKS.map((c, i) => {
              const d = data[c.areaId]; if (!d) return null;
              const bx = 601 - i * TR_BAY_W;
              const by = 563; // Ngoài mặt DOCK
              return (
                <g key={c.areaId}>
                  <ZoneCell c={c} d={d} bx={bx} by={by}
                            bw={TR_BAY_W} bh={Z_H} midLabelY={by+Z_H/2}
                            isHovered={hoveredRack?.areaId===c.areaId}
                            onEnter={() => {
                              setHoveredRack({...c,...d});
                              if (c.zone) setHoveredZone(c.zone);
                            }}
                            onLeave={() => {
                              setHoveredRack(null);
                              setHoveredZone(null);
                            }}
                            onClick={() => {
                              setHoveredRack({...c,...d});
                              if (isMobile) setBottomSheetOpen(true);
                            }}
                            isTruck={true}/>
                  <g pointerEvents="none" opacity="0.8">
                    {/* Quay đầu hướng ra: cabin ở dưới, thùng hàng ở trên */}
                    <rect x={bx+4} y={by+4} width={TR_BAY_W-8} height={Z_H-22}
                          rx="1" fill="rgba(255,255,255,0.15)" stroke="rgba(255,255,255,0.4)" strokeWidth="0.6"/>
                    <rect x={bx+3} y={by+Z_H-16} width={TR_BAY_W-6} height={10}
                          rx="1.5" fill="rgba(255,255,255,0.25)" stroke="rgba(255,255,255,0.5)" strokeWidth="0.7"/>
                  </g>
                </g>
              );
            })}
            <rect x={181} y={563} width={448} height={Z_H} rx="2"
                  {...getZoneBorderProps(1, '--orange')}/>

          </g>

          {/* Inbound Trucks (Xe chờ xuống tải đối diện cổng A13-A18) */}
          <g>
            {INBOUND_TRUCKS.map((c) => {
              const d = data[c.areaId] || { current: 0, capacity: 780, remaining: 780, utilization: 0, bucket: 'green', name: c.name };
              const bx = c.bx;
              const by = 563; // Ngoài mặt DOCK
              const isTrHovered = hoveredRack?.areaId===c.areaId || hoveredZone===4;
              return (
                <g key={c.areaId}>
                  <ZoneCell c={c} d={d} bx={bx} by={by}
                            bw={TR_BAY_W} bh={Z_H} midLabelY={by+Z_H/2}
                            isHovered={isTrHovered}
                            onEnter={() => {
                              setHoveredRack({...c,...d});
                              setHoveredZone(4);
                            }}
                            onLeave={() => {
                              setHoveredRack(null);
                              setHoveredZone(null);
                            }}
                            onClick={() => {
                              setHoveredRack({...c,...d});
                              if (isMobile) setBottomSheetOpen(true);
                            }}
                            isTruck={true}/>
                  <g pointerEvents="none" opacity="0.8">
                    {/* Quay đầu hướng ra: cabin ở dưới, thùng hàng ở trên */}
                    <rect x={bx+4} y={by+4} width={TR_BAY_W-8} height={Z_H-22}
                          rx="1" 
                          fill={hoveredZone === 4 ? "rgba(96,165,250,0.3)" : "rgba(96,165,250,0.15)"} 
                          stroke={hoveredZone === 4 ? "rgba(96,165,250,0.8)" : "rgba(96,165,250,0.4)"} 
                          strokeWidth={hoveredZone === 4 ? 1.0 : 0.6}/>
                    <rect x={bx+3} y={by+Z_H-16} width={TR_BAY_W-6} height={10}
                          rx="1.5" 
                          fill={hoveredZone === 4 ? "rgba(96,165,250,0.45)" : "rgba(96,165,250,0.25)"} 
                          stroke={hoveredZone === 4 ? "rgba(96,165,250,0.9)" : "rgba(96,165,250,0.5)"} 
                          strokeWidth={hoveredZone === 4 ? 1.1 : 0.7}/>
                  </g>
                </g>
              );
            })}
            <rect x={653} y={563} width={188} height={Z_H} rx="2"
                  {...getZoneBorderProps(4, '--inbound')}/>
          </g>

          <g onMouseEnter={() => setHoveredZone(4)}
             onMouseLeave={() => setHoveredZone(null)}
             className="cursor-pointer">
            <text x={(IB_XL1+IB_XL2+IB_LW)/2} y={IB_Y-6} textAnchor="middle"
                  fill="var(--inbound)" className="disp text-[7.5px] font-bold tracking-wider">
              INBOUND SORT L1
            </text>

            {[IB_XL1, IB_XL2].map((lx, li) => {
              const isL1Hovered = hoveredZone === 4;
              return (
                <g key={li}>
                  <rect x={lx} y={IB_Y} width={IB_LW} height={IB_H}
                        rx="2" fill="rgba(96,165,250,0.05)"
                        stroke="var(--inbound)" 
                        strokeWidth={isL1Hovered ? 1.8 : 1.1} 
                        strokeOpacity={isL1Hovered ? 1.0 : 0.6}
                        strokeDasharray={isL1Hovered ? "none" : "3 2"}
                        style={{ transition: 'all 0.25s ease' }}/>

                  {IB_NAMES.map((name, si) => {
                    const sx = lx + si * IB_SW;
                    return (
                      <g key={`${li}-${si}`}>
                        <rect x={sx+0.5} y={IB_Y} width={IB_SW-1} height={IB_H}
                              fill="rgba(96,165,250,0.07)" stroke="rgba(96,165,250,0.2)" strokeWidth="0.5"/>
                        <rect x={sx+1.5} y={IB_Y+IB_H-12} width={IB_SW-3} height={10}
                              rx="1" fill="rgba(96,165,250,0.2)" stroke="rgba(96,165,250,0.4)" strokeWidth="0.5"/>
                        <line x1={sx+IB_SW/2-2} y1={IB_Y+IB_H-12} x2={sx+IB_SW/2-2} y2={IB_Y+IB_H-2}
                              stroke="rgba(96,165,250,0.3)" strokeWidth="0.4"/>
                        <line x1={sx+IB_SW/2+2} y1={IB_Y+IB_H-12} x2={sx+IB_SW/2+2} y2={IB_Y+IB_H-2}
                              stroke="rgba(96,165,250,0.3)" strokeWidth="0.4"/>
                        <text x={sx+IB_SW/2} y={IB_Y+IB_H/2-3} textAnchor="middle"
                              fill="var(--inbound)" className="mono text-[5px]"
                              transform={`rotate(-90 ${sx+IB_SW/2} ${IB_Y+IB_H/2-3})`}>{name}</text>
                      </g>
                    );
                  })}
                </g>
              );
            })}

            <path d={`M ${IB_XL1+IB_LW/2},${DOCK_Y+12} L ${IB_XL1+IB_LW/2},${IB_Y+IB_H-2}`} fill="none" stroke="rgba(96,165,250,0.45)" strokeWidth="1.2" strokeDasharray="3 2" markerEnd="url(#arrow-blue)"/>
            <path d={`M ${IB_XL2+IB_LW/2},${DOCK_Y+12} L ${IB_XL2+IB_LW/2},${IB_Y+IB_H-2}`} fill="none" stroke="rgba(96,165,250,0.45)" strokeWidth="1.2" strokeDasharray="3 2" markerEnd="url(#arrow-blue)"/>
          </g>

          <rect x={WL} y={DOCK_Y} width={WR-WL} height={DOCK_H}
                fill="rgba(31,45,77,0.75)" stroke="#3c5285" strokeWidth="1.5"/>
          <rect x={WL} y={DOCK_Y} width={WR-WL} height={DOCK_H}
                fill="url(#dock-stripe)" pointerEvents="none"/>
          <text x={(WL+WR)/2} y={DOCK_Y+DOCK_H/2+4} textAnchor="middle"
                fill="#9fb4d6" className="mono font-bold text-[8px] tracking-wider"
                pointerEvents="none">DOCK (7.8M)</text>

          <g>
            {[
              { id: 'A1-A2', x: 167, w: 74, type: 'outbound' },
              { id: 'A3-A4', x: 252, w: 74, type: 'outbound' },
              { id: 'A5', x: 338, w: 25, type: 'outbound' },
              { id: 'A6', x: 375, w: 25, type: 'outbound' },
              { id: 'A7', x: 412, w: 25, type: 'outbound' },
              { id: 'A8', x: 449, w: 25, type: 'outbound' },
              { id: 'A9-A10', x: 486, w: 74, type: 'outbound' },
              { id: 'A11-A12', x: 572, w: 74, type: 'outbound' },
              { id: 'A13-A14', x: 663, w: 74, type: 'inbound' },
              { id: 'A15-A16', x: 748, w: 74, type: 'inbound' },
              { id: 'A17', x: 833, w: 25, type: 'inbound' },
              { id: 'A18', x: 869, w: 25, type: 'inbound' }
            ].map(g => (
              <g key={g.id} className="cursor-pointer hover:opacity-80"
                 onMouseEnter={() => setHoveredZone(g.type === 'inbound' ? 4 : 1)}
                 onMouseLeave={() => setHoveredZone(null)}>
                <rect x={g.x} y={DOCK_Y+8} width={g.w} height={DOCK_H-16}
                      rx="1"
                      fill={g.type==='inbound'?(g.id==='A18'?'rgba(96,165,250,0.22)':'rgba(96,165,250,0.12)'):'rgba(249,115,22,0.12)'}
                      stroke={g.type==='inbound'?'var(--inbound)':'var(--orange)'}
                      strokeWidth={g.id==='A18'?1.4:0.8}/>
                <text x={g.x+g.w/2} y={DOCK_Y+DOCK_H/2+3} textAnchor="middle"
                      fill="#fff" className="mono text-[5.5px] font-bold tracking-tight">{g.id}</text>
              </g>
            ))}
          </g>

          {/* ── Gate A18 arrow (entry to NS path) ── */}
          <path d={`M${NS_X+NS_W/2},${DOCK_Y+DOCK_H-8} L${NS_X+NS_W/2},${WB-4}`}
                fill="none" stroke="rgba(96,165,250,0.6)" strokeWidth="1.5"
                strokeDasharray="3 2" markerEnd="url(#arrow-blue)"/>
          <text x={NS_X-2} y={WB+25} fill="rgba(96,165,250,0.75)"
                className="mono text-[5px] font-bold">VÀO ĐƯỜNG ĐI (A18)</text>

          
          </g>
        </svg>
    );
  };

  return (
    <div className="w-full h-full relative font-sans text-white bg-[#02040a]">
      {!isMobile && (
        <div className="absolute top-0 right-0 h-14 flex items-center justify-between px-6 z-50 transition-all duration-300 left-16 pointer-events-none"
             style={{ background: 'transparent' }}>
          <div className="flex items-center select-none" />
          <div className="flex items-center gap-4 pointer-events-auto">
            {lastUpdate && currentView === 'master' && (
              <div style={{ 
                fontSize: '11px', 
                color: '#B8F7E4', 
                background: 'rgba(184, 247, 228, 0.05)', 
                border: '1px solid rgba(184, 247, 228, 0.2)', 
                padding: '5px 14px', 
                borderRadius: '20px', 
                fontWeight: 600, 
                fontFamily: "'Inter', sans-serif",
                display: 'flex',
                alignItems: 'center',
                gap: '6px',
                textShadow: '0 0 8px rgba(184,247,228,0.3)'
              }}>
                <span className="w-1.5 h-1.5 rounded-full bg-[#10b981] animate-pulse" />
                Update: {lastUpdate}
              </div>
            )}

            {/* ── LAYOUT / KPI / HEATMAP DatePicker: (Chỉ hiển thị khi KHÔNG PHẢI view InboundDashboard, vì InboundDashboard đã có header riêng) ── */}
            {currentView !== 'inbound' && (
              <div className="flex items-center gap-2">
                <span className="text-xs text-slate-400 font-semibold select-none">Operations Date</span>
                <DatePicker
                  selectedDate={selectedDate}
                  onDateChange={(d) => setSelectedDate(d)}
                  availableDates={availableDates}
                  align="right"
                  className="w-[210px]"
                  buttonClassName="!py-1.5 !px-4 !rounded-full text-xs font-bold"
                />
              </div>
            )}
          </div>
        </div>
      )}

      {!isMobile ? (
        /* ── DESKTOP LAYOUT ── */
        <>
          {/* Sidebar Menu - Hover Collapsible with 30% Compact Width (w-40) & Dashboard Theme Colors */}
          <div 
            onMouseEnter={() => setSidebarHovered(true)}
            onMouseLeave={() => setSidebarHovered(false)}
            className={`fixed top-0 left-0 h-full z-40 flex flex-col bg-[#121519]/95 backdrop-blur-xl border-r border-white/[0.08] font-outfit select-none transition-all duration-200 ${
              sidebarHovered ? 'w-40' : 'w-12'
            }`}
            style={{ fontFamily: "'Outfit', sans-serif" }}
          >
            {/* Sidebar Header - Fixed w-12 slot for 100% pixel alignment */}
            <div className="flex items-center border-b border-white/[0.08] h-12 select-none shrink-0">
              <div className="w-12 h-full flex items-center justify-center shrink-0">
                <Menu size={18} className="text-slate-200" />
              </div>
              {sidebarHovered && (
                <span className="text-[17px] font-black text-slate-100 tracking-tight font-outfit pr-3 whitespace-nowrap">Menu</span>
              )}
            </div>

            {/* Menu Items */}
            <div className="flex-1 py-3 space-y-3 px-0 overflow-y-auto scrollbar-none font-outfit" style={{ scrollbarWidth: 'none' }}>
              
              {/* Group 1: DASHBOARD VIEWS (Fixed w-12 slot - Text starts at exact 48px) */}
              <div className="space-y-1 font-outfit">
                {[
                  { id: 'master', label: 'Layout', color: '#4F8CFF', active: currentView === 'master', onClick: () => setCurrentView('master') },
                  { id: 'inbound', label: 'Inbound', color: '#B8F7E4', active: currentView === 'inbound', onClick: () => setCurrentView('inbound') },
                  { id: 'heatmap', label: 'Heatmap', color: '#B8F7E4', active: currentView === 'heatmap', onClick: () => setCurrentView('heatmap') },
                  { id: 'kpi', label: 'KPI', color: '#F59E0B', active: currentView === 'kpi', onClick: () => setCurrentView('kpi') },
    { id: 'maps', label: 'Maps', color: '#00F2FE', active: currentView === 'maps', onClick: () => setCurrentView('maps') },
                ].map(item => {
                  return (
                    <button
                      key={item.id}
                      onClick={item.onClick}
                      className={`w-full h-10 flex items-center text-left transition-all duration-150 font-outfit relative rounded-r-sm ${
                        item.active 
                          ? 'bg-[#2c303a] font-extrabold shadow-sm' 
                          : 'text-[#94A3B8] hover:text-white hover:bg-white/[0.04] font-semibold'
                      }`}
                      style={item.active ? { 
                        color: item.color,
                        boxShadow: `0 0 10px ${item.color}20`,
                        fontFamily: "'Outfit', sans-serif" 
                      } : { fontFamily: "'Outfit', sans-serif" }}
                    >
                      {item.active && (
                        <div 
                          className="absolute left-0 top-0 bottom-0 w-[3px] rounded-r-sm"
                          style={{ backgroundColor: item.color }}
                        />
                      )}
                      
                      {/* Left w-12 Slot */}
                      <div className="w-12 h-full flex items-center justify-center shrink-0">
                        {!sidebarHovered && (
                          <span className="text-xs font-black text-center font-outfit" style={{ color: item.active ? item.color : '#94A3B8' }}>
                            {item.label.charAt(0)}
                          </span>
                        )}
                      </div>

                      {/* Text Label - Starts at 48px */}
                      {sidebarHovered && (
                        <span className="text-[15px] font-extrabold tracking-tight font-outfit pr-3 whitespace-nowrap" style={{ color: item.active ? item.color : undefined }}>
                          {item.label}
                        </span>
                      )}
                    </button>
                  );
                })}
              </div>

              {/* Group 2: PANEL / TIỆN ÍCH (Fixed w-12 slot - Text starts at exact 48px) */}
              {currentView === 'master' && (
                <div className="space-y-0.5 pt-2.5 border-t border-white/[0.08] font-outfit">
                  {sidebarHovered && (
                    <div className="flex items-center h-6 select-none">
                      <div className="w-12 shrink-0" />
                      <span className="text-[10px] text-slate-400 font-semibold tracking-[0.08em] uppercase pr-3 font-outfit whitespace-nowrap">
                        PANEL / TIỆN ÍCH
                      </span>
                    </div>
                  )}
                  {[
                    { id: 'monitor', label: 'Giám sát phân khu', active: showMonitor, onClick: () => setShowMonitor(!showMonitor) },
                    { id: 'telemetry', label: 'Thông số kho', active: showTelemetry, onClick: () => setShowTelemetry(!showTelemetry) },
                    { id: 'controls', label: 'Bộ lọc dữ liệu', active: showControls, onClick: () => setShowControls(!showControls) },
                    { id: 'top10', label: 'Bảng xếp hạng', active: showTop10, onClick: () => setShowTop10(!showTop10) },
                  ].map(item => {
                    return (
                      <button
                        key={item.id}
                        onClick={item.onClick}
                        className={`w-full h-8 flex items-center rounded-r-sm text-left transition-all duration-150 font-outfit ${
                          item.active 
                            ? 'text-white bg-[#2c303a] font-normal shadow-sm' 
                            : 'text-[#94A3B8] hover:text-white hover:bg-white/[0.04] font-normal'
                        }`}
                        style={{ fontFamily: "'Outfit', sans-serif" }}
                      >
                        {/* Left w-12 Slot */}
                        <div className="w-12 h-full flex items-center justify-center shrink-0">
                          {!sidebarHovered && (
                            <span className="text-[10px] font-normal text-slate-400 font-outfit">{item.label.substring(0, 2)}</span>
                          )}
                        </div>

                        {/* Text Label - Starts at 48px */}
                        {sidebarHovered && (
                          <span className="text-[13px] font-normal tracking-normal whitespace-nowrap font-outfit text-slate-300 pr-3">{item.label}</span>
                        )}
                      </button>
                    );
                  })}
                </div>
              )}

            </div>
          </div>

          {/* Logo J&T Cargo - absolute top-left, above left panels */}
          {currentView === 'master' && (
            <div
              className="absolute z-30 select-none transition-all duration-200"
              style={{ top: '14px', left: sidebarHovered ? '176px' : '64px' }}
            >
              <img src="logo.png" alt="J&T Cargo Logo" className="jt-logo" style={{ height: '72px', display: 'block' }} />
            </div>
          )}

          {/* Left Column: Stacked panels (w-72) */}
          {currentView === 'master' && (
            <div 
              className="absolute z-20 top-[104px] w-72 flex flex-col gap-4 max-h-[calc(100vh-120px)] overflow-y-auto pr-2 pb-6 scrollbar-thin transition-all duration-200"
              style={{ left: sidebarHovered ? '176px' : '64px' }}
            >
              
              {/* 1. OPERATIONAL MONITOR & ZONE METRICS */}
              {showMonitor && (
                <div className="jt-glowing-card shadow-2xl shrink-0" style={{ padding: '18px 20px', background: 'rgba(255,255,255,0.03)' }}>

                  {/* Title */}
                  <div className="font-bold text-[13px] tracking-[0.15em] text-center" style={{ color: '#FFF4D6', fontFamily: "'Inter', sans-serif", marginBottom: '14px', textShadow: '0 0 12px rgba(255,244,214,0.3)' }}>
                    OPERATIONAL MONITOR
                  </div>

                  {/* Tỉ lệ lấp đầy - full width with UTILCOL warning */}
                  {(() => {
                    const utilNum = Number(utilTotal);
                    const utilBucket = utilNum > 100 ? 'darkred' : utilNum >= 95 ? 'red' : utilNum >= 80 ? 'orange' : utilNum >= 50 ? 'yellow' : 'green';
                    const utilColor = UTILCOL[utilBucket];
                    return (
                      <div style={{ background: `${utilColor}12`, border: `1px solid ${utilColor}40`, borderRadius: '10px', padding: '12px 16px', marginBottom: '10px' }}>
                        <div style={{ fontSize: '10px', fontWeight: 700, letterSpacing: '0.14em', color: '#e2e8f0', marginBottom: '6px', fontFamily: "'Inter',sans-serif" }}>{displayUtilizationLabel}</div>
                        <div className="flex items-center gap-3">
                          <div style={{ flex: 1, height: '8px', borderRadius: '99px', background: 'rgba(255,255,255,0.1)', overflow: 'hidden' }}>
                            <div style={{ height: '100%', borderRadius: '99px', background: utilColor, width: `${Math.min(100, utilNum)}%`, transition: 'width 1s ease' }} />
                          </div>
                          <div className="mono font-bold" style={{ fontSize: '18px', lineHeight: 1, color: utilColor, minWidth: '44px', textAlign: 'right', textShadow: `0 0 10px ${utilColor}99` }}>{utilTotal}%</div>
                        </div>
                      </div>
                    );
                  })()}
                  <div style={{ background: 'rgba(255,255,255,0.04)', border: '1px solid rgba(255,255,255,0.1)', borderRadius: '8px', padding: '7px 10px', marginBottom: '8px' }}>
                    <div style={{ fontSize: '8px', fontWeight: 700, letterSpacing: '0.12em', color: '#94a3b8', fontFamily: "'Inter',sans-serif", marginBottom: '2px' }}>Ô ĐANG DÙNG</div>
                    <div className="mono font-bold" style={{ fontSize: '16px', lineHeight: 1, color: '#f1f5f9' }}>{usedCells}<span style={{ fontSize: '11px', color: '#64748b' }}>/{CHUTE_RACKS.length}</span></div>
                  </div>
                  {(() => {
                    const obNum = Number(outboundRate);
                    const obBucket = obNum > 100 ? 'darkred' : obNum >= 95 ? 'red' : obNum >= 80 ? 'orange' : obNum >= 50 ? 'yellow' : 'green';
                    const obColor = UTILCOL[obBucket];
                    return (
                      <div style={{ background: `${obColor}10`, border: `1px solid ${obColor}35`, borderRadius: '8px', padding: '7px 10px', marginBottom: '10px' }}>
                        <div style={{ fontSize: '8px', fontWeight: 700, letterSpacing: '0.12em', color: '#94a3b8', fontFamily: "'Inter',sans-serif", marginBottom: '2px' }}>TỈ LỆ OUTBOUND</div>
                        <div className="mono font-bold" style={{ fontSize: '16px', lineHeight: 1, color: obColor, textShadow: `0 0 8px ${obColor}88` }}>{outboundRate}%</div>
                      </div>
                    );
                  })()}

                  {/* Zone cards 3-column grid */}

                  <div className="grid grid-cols-3 gap-2 mb-4">
                    {[
                      { id: 3, shortName: 'ZONE 3', sub: '', color: '#B8F7E4', colorBg: 'rgba(16,185,129,0.1)', colorBorder: 'rgba(16,185,129,0.3)' },
                      { id: 2, shortName: 'ZONE 2', sub: '', color: '#f59e0b', colorBg: 'rgba(245,158,11,0.1)', colorBorder: 'rgba(245,158,11,0.3)' },
                      { id: 1, shortName: 'ZONE 1', sub: '', color: '#f97316', colorBg: 'rgba(249,115,22,0.1)', colorBorder: 'rgba(249,115,22,0.3)' }
                    ].map(zone => {
                      const stats = zoneStats[zone.id];
                      const isHovered = hoveredZone === zone.id;
                      return (
                        <div
                          key={zone.id}
                          style={{
                            background: isHovered ? zone.colorBg : 'rgba(255,255,255,0.04)',
                            border: `1px solid ${isHovered ? zone.colorBorder : 'rgba(255,255,255,0.12)'}`,
                            borderRadius: '10px', padding: '12px 6px',
                            cursor: 'pointer', transition: 'all 0.25s ease',
                            boxShadow: isHovered ? `0 0 16px ${zone.color}33` : 'none',
                            textAlign: 'center',
                            display: 'flex', flexDirection: 'column', gap: '6px', alignItems: 'center'
                          }}
                          onMouseEnter={() => setHoveredZone(zone.id)}
                          onMouseLeave={() => setHoveredZone(null)}
                        >
                          <div className="mono font-extrabold" style={{ fontSize: '13px', color: zone.color, lineHeight: 1.2, textShadow: `0 0 8px ${zone.color}88` }}>{zone.shortName}</div>
                          <div className="mono font-bold" style={{ fontSize: '13px', color: zone.color, lineHeight: 1.2 }}>{stats.fillRate}%</div>
                          <div className="mono font-bold" style={{ fontSize: '13px', color: '#B8F7E4', lineHeight: 1.2 }}>{stats.current.toLocaleString()}</div>
                          <div className="mono font-bold" style={{ fontSize: '13px', color: '#f1f5f9', lineHeight: 1.2 }}>{(stats as any).totalShare}%</div>
                          <div className="mono font-bold" style={{ fontSize: '13px', color: '#B8F7E4', lineHeight: 1.2 }}>{stats.weight.toFixed(1).replace('.', ',')} Tấn</div>
                        </div>
                      );
                    })}
                  </div>

                  {/* Chi tiết ô chứa */}
                  <div style={{ borderTop: '1px solid rgba(255,255,255,0.1)', paddingTop: '12px' }}>
                    <div style={{ fontSize: '10px', fontWeight: 700, letterSpacing: '0.14em', color: '#cbd5e1', marginBottom: '8px', fontFamily: "'Inter',sans-serif" }}>CHI TIẾT Ô CHỨA</div>
                    {hoveredRack ? (
                      <div style={{ background: 'rgba(255,255,255,0.04)', borderRadius: '8px', padding: '10px', border: '1px solid rgba(255,255,255,0.1)' }}>
                        {[
                          ['Mã ô', hoveredRack.areaId, 'var(--cyan)'],
                          ['Tên', hoveredRack.name, '#f1f5f9'],
                          ['Số lượng', `${hoveredRack.current}/${hoveredRack.capacity} Đơn hàng`, '#f1f5f9'],
                          ['Trọng lượng', `${((hoveredRack.weight || 0) > 0 && (hoveredRack.weight || 0) < 0.1) ? (hoveredRack.weight || 0).toFixed(3).replace('.', ',') : (hoveredRack.weight || 0).toFixed(1).replace('.', ',')} Tấn`, '#f1f5f9'],
                          [displayUtilizationLabelLc, `${hoveredRack.utilization}%`, UTILCOL[hoveredRack.bucket]]
                        ].map(([k, v, c]) => (
                          <div key={k} className="flex justify-between" style={{ marginBottom: '4px' }}>
                            <span style={{ fontSize: '10px', color: '#94a3b8' }}>{k}:</span>
                            <span className="mono font-bold" style={{ fontSize: '10px', color: c, maxWidth: '130px', overflow: 'hidden', textOverflow: 'ellipsis' }}>{v}</span>
                          </div>
                        ))}
                      </div>
                    ) : (
                      <div style={{ textAlign: 'center', padding: '10px', fontSize: '10px', color: '#94a3b8', border: '1px dashed rgba(255,255,255,0.15)', borderRadius: '8px' }}>
                        Rê chuột vào ô để xem thông tin chi tiết
                      </div>
                    )}
                  </div>
                </div>
              )}

              {showTelemetry && (
                <div className="jt-glowing-card shadow-2xl shrink-0 w-full" style={{ padding: '12px 16px', background: 'rgba(255,255,255,0.04)' }}>
                  <div className="font-bold text-[13px] tracking-[0.15em] text-center" style={{ color: '#FFF4D6', fontFamily: "'Inter', sans-serif", marginBottom: '10px', textShadow: '0 0 12px rgba(255,244,214,0.3)' }}>
                    METRICS
                  </div>
                  <div style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
                    <div className="flex justify-between items-center">
                      <span style={{ fontSize: '13px', color: '#cbd5e1', fontFamily: "'Inter',sans-serif", fontWeight: 600 }}>Tổng đơn hàng</span>
                      <span className="mono font-bold" style={{ fontSize: '15px', color: '#B8F7E4', textShadow: '0 0 10px rgba(184,247,228,0.5)' }}>
                        <NumberTicker value={totalOrders} /> <span style={{ fontSize: '12px', color: '#94a3b8', fontWeight: 500 }}>Đơn</span>
                      </span>
                    </div>
                    <div className="flex justify-between items-center">
                      <span style={{ fontSize: '13px', color: '#cbd5e1', fontFamily: "'Inter',sans-serif", fontWeight: 600 }}>Tổng trọng lượng</span>
                      <span className="mono font-bold" style={{ fontSize: '15px', color: '#B8F7E4', textShadow: '0 0 10px rgba(184,247,228,0.5)' }}>
                        {(totalWeight > 0 && totalWeight < 0.1) ? totalWeight.toFixed(3).replace('.', ',') : totalWeight.toFixed(1).replace('.', ',')} <span style={{ fontSize: '12px', color: '#94a3b8', fontWeight: 500 }}>Tấn</span>
                      </span>
                    </div>
                  </div>
                </div>
              )}

              {/* ── LINEHAUL Forecast Table ── */}
              {showTelemetry && (() => {
                // 🎯 Đọc trực tiếp từ microKpiSummary để Dự kiến SL LINEHAUL đồng bộ 100% với Inbound Dashboard
                const linehaulOrders = microKpiSummary?.linehaul ?? (data['A06']?.current ?? 0);
                const linehaulWeight = microKpiSummary?.linehaul_weight ?? (data['A06']?.weight ?? 0);

                const bnRows = [
                  {
                    name: 'BN HUB',
                    orders: linehaulOrders,
                    weightTon: linehaulWeight,
                  }
                ].filter(r => r.orders > 0);

                const totOrders = bnRows.reduce((s, r) => s + r.orders, 0);
                const totWeight = bnRows.reduce((s, r) => s + r.weightTon, 0);

                // 🎯 Denominator % VOL = Forecast Total (microKpiSummary?.forecast_total)
                const fcTotal = microKpiSummary?.forecast_total && microKpiSummary.forecast_total > 0
                  ? microKpiSummary.forecast_total
                  : (totalOrders > 0 ? totalOrders : 1);

                const grandTotal = fcTotal;
                const totalPct = ((totOrders / grandTotal) * 100).toFixed(1);

                // 🔥🧊 Warm-Cool Balance Palette
                const C_HEADER   = '#f97316'; // Orange 🔥  — header title (brand/identity)
                const C_BADGE    = '#22d3ee'; // Cyan   🧊  — badge (contrast điểm nhấn)
                // C_TOT_LBL removed — TỔNG CỘNG row now uses C_TOT_VAL for all cells
                const C_TOT_VAL  = '#67e8f9'; // Ice Cyan  — TỔNG CỘNG values
                const C_ORDERS   = '#fbbf24'; // Amber  🔥  — ĐƠN (số quan trọng nhất, warm)
                const C_WEIGHT   = '#818cf8'; // Indigo 🧊  — T.LƯỢNG (cool)
                const C_PCT      = '#34d399'; // Emerald🧊  — % VOL (cool)

                return (
                  <div className="jt-glowing-card shadow-2xl shrink-0 w-full"
                    style={{ marginTop: '20px', padding: '12px 16px', background: 'rgba(255,255,255,0.04)', overflow: 'hidden', borderTop: '1px solid rgba(249,115,22,0.25)', borderBottom: '1px solid rgba(34,211,238,0.2)' }}>
                    {/* Header — warm title 🔥 + cool badge 🧊 */}
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '10px', paddingBottom: '8px', borderBottom: '1px solid rgba(249,115,22,0.2)' }}>
                      <span style={{ fontSize: '11px', fontWeight: 800, letterSpacing: '0.12em', textTransform: 'uppercase', color: C_HEADER, fontFamily: "'Inter',sans-serif", textShadow: `0 0 10px ${C_HEADER}60` }}>
                        🔶 Dự kiến SL LINEHAUL
                      </span>
                      <span style={{ fontSize: '10px', fontWeight: 700, color: C_BADGE, background: `${C_BADGE}18`, border: `1px solid ${C_BADGE}45`, borderRadius: '10px', padding: '2px 8px' }}>
                        {totOrders.toLocaleString()} Đơn
                      </span>
                    </div>
                    {/* Table */}
                    <table style={{ width: '100%', borderCollapse: 'collapse' }}>
                      <thead>
                        <tr style={{ borderBottom: '1px solid rgba(255,255,255,0.06)' }}>
                          {(['HUB', 'ĐƠN', 'T.LƯỢNG', '% VOL'] as const).map((h, i) => (
                            <th key={h} style={{ padding: '3px 4px', fontSize: '8.5px', fontWeight: 700, letterSpacing: '0.1em', color: '#94a3b8', textAlign: i === 0 ? 'left' : 'right', fontFamily: "'Inter',sans-serif" }}>{h}</th>
                          ))}
                        </tr>
                      </thead>
                      <tbody>
                        {/* Total row — warm label, cool values */}
                        {totOrders > 0 && (
                          <tr style={{ background: 'rgba(103,232,249,0.07)', borderBottom: '1px solid rgba(103,232,249,0.18)' }}>
                            <td style={{ padding: '5px 4px', fontWeight: 800, color: C_TOT_VAL, fontSize: '10px', fontFamily: "'Inter',sans-serif" }}>TỔNG CỘNG</td>
                            <td className="mono" style={{ textAlign: 'right', padding: '5px 4px', fontWeight: 800, color: C_TOT_VAL, fontSize: '11px' }}>{totOrders.toLocaleString()}</td>
                            <td className="mono" style={{ textAlign: 'right', padding: '5px 4px', fontWeight: 800, color: C_TOT_VAL, fontSize: '11px' }}>{totWeight.toFixed(1)}T</td>
                            <td className="mono" style={{ textAlign: 'right', padding: '5px 4px', fontWeight: 800, color: C_TOT_VAL, fontSize: '11px' }}>{totalPct}%</td>
                          </tr>
                        )}
                        {bnRows.map(row => {
                          const pct = ((row.orders / grandTotal) * 100).toFixed(1);
                          return (
                            <tr key={row.name} style={{ borderBottom: '1px solid rgba(255,255,255,0.04)' }}>
                              <td style={{ padding: '4px 4px', color: '#cbd5e1', fontSize: '10px', fontWeight: 600, fontFamily: "'Inter',sans-serif" }}>{row.name}</td>
                              <td className="mono" style={{ textAlign: 'right', padding: '4px 4px', color: C_ORDERS, fontWeight: 700, fontSize: '11px' }}>{row.orders.toLocaleString()}</td>
                              <td className="mono" style={{ textAlign: 'right', padding: '4px 4px', color: C_WEIGHT, fontSize: '11px' }}>{row.weightTon.toFixed(1)}T</td>
                              <td className="mono" style={{ textAlign: 'right', padding: '4px 4px', color: C_PCT, fontSize: '11px' }}>{pct}%</td>
                            </tr>
                          );
                        })}
                        {bnRows.length === 0 && (
                          <tr><td colSpan={4} style={{ textAlign: 'center', padding: '14px 4px', color: '#475569', fontSize: '10px' }}>Không có dữ liệu Linehaul</td></tr>
                        )}
                      </tbody>
                    </table>
                  </div>
                );
              })()}







            </div>
          )}

          {/* Right Column: Control Center & Top 10 Racks (w-90, 15px gap, 10% rounded corners) */}
          {currentView === 'master' && (
            <div className="absolute z-40 top-16 right-6 w-90 flex flex-col gap-[15px] max-h-[calc(100vh-120px)] overflow-y-auto pr-2 pb-6 scrollbar-none">
              {/* A. Control Center Panel (Chỉ hiển thị khi xem Sơ đồ Master, không hiển thị chồng lên Inbound Dashboard) */}
              {currentView === 'master' && showControls && (
                <div 
                  className="jt-glowing-card shadow-2xl p-4 shrink-0 relative z-20 rounded-lg"
                  style={{ borderRadius: '8px' }}
                >
                  {currentView === 'master' ? (
                    <>
                      <h3 className="font-outfit text-[13px] font-bold tracking-[0.08em] pb-2 mb-2.5 border-b border-white/[0.08] text-center" style={{ margin: 0, color: '#FFF4D6', textShadow: '0 0 12px rgba(255,244,214,0.3)' }}>CONTROL CENTER</h3>
                      <div className="flex flex-col gap-[4px]">
                        {/* 1. LOẠI (Type Selector) - Segmented Control */}
                        <div className="flex bg-black/35 rounded-lg p-0.5 w-full">
                          {(['Outbound', 'Backlog', 'Inventory'] as const).map(type => {
                            const isActive = selectedType === type;
                            const labelMap = { Outbound: 'Outbound', Backlog: 'Backlog', Inventory: 'Volume' };
                            return (
                              <button
                                key={type}
                                onClick={() => setSelectedType(type)}
                                className={`flex-1 text-center py-1.5 rounded-md text-[11.5px] font-bold transition-all duration-200 relative z-10 ${
                                  isActive
                                    ? 'text-white bg-emerald-500/20 shadow-[0_2px_8px_rgba(16,185,129,0.25)]'
                                    : 'text-slate-400 hover:text-white hover:bg-white/5'
                                }`}
                              >
                                {labelMap[type]}
                              </button>
                            );
                          })}
                        </div>

                        {/* 2. TRẠNG THÁI (Status Selector) - CHIP style with checkmarks */}
                        <div className={`grid grid-cols-2 gap-[2px] transition-all duration-300 ${
                          selectedType !== 'Inventory' ? 'opacity-30 pointer-events-none select-none filter blur-[0.4px]' : 'opacity-100'
                        }`}>
                          <button
                            onClick={toggleAllStatuses}
                            className={`flex items-center justify-center gap-1.5 px-2 py-1.5 rounded-lg text-[11.5px] font-bold transition-all duration-200 ${
                              selectedStatuses.length === INVENTORY_STATUSES.length
                                ? 'bg-emerald-500/15 text-emerald-400 border border-emerald-500/30 shadow-[0_4px_12px_rgba(0,0,0,0.3),_0_0_8px_rgba(16,185,129,0.15)] hover:translate-y-[-1px]'
                                : 'bg-white/[0.04] border border-white/5 text-slate-400 hover:bg-white/[0.07] hover:text-white hover:translate-y-[-1px]'
                            }`}
                          >
                            {selectedStatuses.length === INVENTORY_STATUSES.length && <i className="fa-solid fa-check text-[10px] text-emerald-400"></i>}
                            <span>Total</span>
                          </button>
                          {INVENTORY_STATUSES.map(status => {
                            const isChecked = selectedStatuses.includes(status);
                            return (
                              <button
                                key={status}
                                onClick={() => toggleStatus(status)}
                                className={`flex items-center justify-center gap-1.5 px-2 py-1.5 rounded-lg text-[11.5px] font-bold transition-all duration-200 ${
                                  isChecked
                                    ? 'bg-emerald-500/15 text-emerald-400 border border-emerald-500/30 shadow-[0_4px_12px_rgba(0,0,0,0.3),_0_0_8px_rgba(16,185,129,0.15)] hover:translate-y-[-1px]'
                                    : 'bg-white/[0.04] border border-white/5 text-slate-400 hover:bg-white/[0.07] hover:text-white hover:translate-y-[-1px]'
                                }`}
                              >
                                {isChecked && <i className="fa-solid fa-check text-[10px] text-emerald-400"></i>}
                                <span>{status}</span>
                              </button>
                            );
                          })}
                        </div>
                      </div>
                    </>
                  ) : (
                    <>
                      <h3 className="disp text-xs tracking-[0.14em] pb-3 mb-4 border-b border-[var(--line)] text-[#8B5CF6]">OPERATIONS DATE</h3>
                      <div className="space-y-4">
                        {/* Operating Date Selector for Inbound */}
                        <div className="space-y-2">
                          <div className="mono text-[9.5px] tracking-[0.1em] text-slate-400">NGÀY VẬN HÀNH</div>
                          <div className="flex gap-1.5 overflow-x-auto py-1 scrollbar-none" style={{ scrollbarWidth: 'none', msOverflowStyle: 'none' }}>
                            {(() => {
                              const inboundDates = Array.from(
                                new Set([
                                  ...inboundData.map(d => d['Ngày vận hành_Inbound']),
                                  ...inboundData.map(d => d['Ngày vận hành_Forecast']),
                                  ...inboundData.map(d => d['Ngày vận hành_Pickup'])
                                ].filter(Boolean))
                              ) as string[];
                              inboundDates.sort((a, b) => b.localeCompare(a));
                              const activeDate = selectedInboundDate || inboundDates[0] || '';
                              return inboundDates.slice(0, 7).map(d => {
                                const isActive = activeDate === d;
                                return (
                                  <button
                                    key={d}
                                    onClick={() => handleInboundDateChange(d)}
                                    className={`px-3 py-1.5 rounded-full text-[10.5px] font-bold border transition-all duration-250 shrink-0 ${
                                      isActive
                                        ? 'bg-[#2d2440]/60 border-[#8B5CF6] text-[#c084fc] shadow-[0_0_8px_rgba(139,92,246,0.15)]'
                                        : 'bg-[#101622]/40 border-white/5 text-slate-400 hover:border-slate-700/80 hover:text-slate-200'
                                    }`}
                                  >
                                    {d}
                                  </button>
                                );
                              });
                            })()}
                          </div>
                        </div>
                      </div>
                    </>
                  )}
                </div>
              )}

              {/* B. TOP 10 RACKS */}
              {currentView === 'master' && showTop10 && (
                <div 
                  className="jt-glowing-card shadow-2xl p-4 shrink-0 relative z-10 animate-fade-in rounded-lg"
                  style={{ borderRadius: '8px' }}
                >
                  {/* Header Title */}
                  <div className="flex justify-center items-center mb-2.5 pb-2.5 border-b border-white/[0.08]">
                    <h3 className="font-outfit text-[12px] font-bold tracking-[0.08em] text-center" style={{ margin: 0, color: '#FFF4D6', textShadow: '0 0 12px rgba(255,244,214,0.3)' }}>
                      {selectedType === 'Outbound' ? 'DỰ KIẾN SẢN LƯỢNG BƯU CỤC TOP 10' : 'DỰ KIẾN TỒN KHO BƯU CỤC TOP 10'}
                    </h3>
                  </div>

                  <div className="table-wrapper" style={{ maxHeight: '330px', overflowY: 'auto' }}>
                    <table className="jt-grid-table">
                      <thead>
                        <tr style={{ position: 'sticky', top: 0, zIndex: 10 }}>
                          <th style={{ width: '25px', textAlign: 'center' }}>#</th>
                          <th style={{ width: '45px', textAlign: 'center' }}>MÃ</th>
                          <th style={{ textAlign: 'left' }}>BƯU CỤC</th>
                          <th style={{ textAlign: 'center', width: '45px' }}>{selectedType === 'Outbound' ? 'XUẤT' : 'TỒN'}</th>
                          <th style={{ textAlign: 'center', width: '70px' }}>T.LƯỢNG</th>
                          <th style={{ textAlign: 'center', width: '60px' }}>%Volume</th>
                        </tr>
                      </thead>
                      <tbody>
                        {getTop10Chutes().map((chute, index) => {
                          return (
                            <tr key={chute.areaId} className="cursor-pointer"
                                onMouseEnter={() => {
                                  const d = data[chute.areaId];
                                  setHoveredRack({ areaId: chute.areaId, name: chute.name, ...d });
                                  if (chute.zone) setHoveredZone(chute.zone);
                                }}
                                onMouseLeave={() => {
                                  setHoveredRack(null);
                                  setHoveredZone(null);
                                }}>
                              <td className="font-bold text-center text-white" style={{ fontSize: '11px', textShadow: '0 0 6px rgba(255, 255, 255, 0.2)' }}>{index + 1}</td>
                              <td className="mono font-bold text-center" style={{ color: '#22d3ee', fontSize: '11.5px', textShadow: '0 0 8px rgba(34, 211, 238, 0.5)' }}>{chute.areaId}</td>
                              <td className="font-bold uppercase" style={{ color: '#22d3ee', fontSize: '11px', whiteSpace: 'normal', wordBreak: 'break-word', lineHeight: '1.2', textShadow: '0 0 8px rgba(34, 211, 238, 0.3)' }} title={chute.name}>
                                {chute.name}
                              </td>
                              <td className="mono font-bold text-center" style={{ color: '#B8F7E4', fontSize: '12px', textShadow: '0 0 8px rgba(184,247,228,0.5)' }}>{chute.current.toLocaleString()}</td>
                              <td className="mono font-bold text-center text-white" style={{ fontSize: '11px', textShadow: '0 0 6px rgba(255, 255, 255, 0.25)' }}>
                                {(chute.weight > 0 && chute.weight < 0.1) ? chute.weight.toFixed(3) : chute.weight.toFixed(1)} Tấn
                              </td>
                              <td className="mono font-bold text-center" style={{ color: UTILCOL[chute.bucket], fontSize: '11.5px', textShadow: chute.bucket === 'darkred' || chute.bucket === 'red' ? '0 0 8px rgba(239,68,68,0.6)' : '0 0 8px rgba(16,185,129,0.5)' }}>{chute.utilization}%</td>
                            </tr>
                          );
                        })}
                      </tbody>
                    </table>
                  </div>
                </div>
              )}
            </div>
          )}

          {/* Floating Legend */}
          {currentView === 'master' && (
            <div 
              className="absolute bottom-16 z-20 flex gap-3 mono text-[10px] text-[var(--muted)] bg-[var(--panel)] border border-[var(--line)] rounded-lg py-2 px-3 backdrop-blur-md shadow-lg transition-all duration-200"
              style={{ left: sidebarHovered ? '176px' : '64px' }}
            >
              {[['#0c883d','Ô chứa'],['var(--orange)','Cổng Outbound'],
                ['var(--inbound)','Cổng Inbound'],['rgba(100,116,139,0.7)','Xe tải']].map(([c,l])=>(
                <span key={l} className="flex items-center gap-1.5">
                  <i className="w-2.5 h-2.5 rounded-sm" style={{background:c}}/>
                  {l}
                </span>
              ))}
            </div>
          )}

          {/* Aligned bottom right buttons */}
          {currentView === 'master' && (
            <div className="absolute bottom-16 right-6 z-20 flex gap-3 w-[300px] justify-between" >
              {currentView === 'master' ? (
                <button onClick={handleResetZoom}
                        className="flex-1 font-sans font-bold text-[10.5px] uppercase py-2.5 px-4 rounded-md border border-white/20 bg-[var(--panel)] text-[var(--muted)] cursor-pointer hover:bg-white/10 hover:text-white transition-all shadow-lg text-center">
                  THU NHỎ / RESET
                </button>
              ) : (
                <div className="flex-1 p-2 border border-white/5 rounded-md bg-[#101622]/30 text-center flex items-center justify-center">
                  <span className="text-[10px] text-slate-500 uppercase tracking-wider font-bold">Inbound Panel</span>
                </div>
              )}
              <button onClick={fetchAndUpdateData} onMouseMove={handleGoogleBtnMouseMove} disabled={loading}
                      className="flex-1 google-sync-btn justify-center">
                <span className="w-1.5 h-1.5 rounded-full bg-[#22c55e] animate-pulse shrink-0" />
                {loading ? 'Đang đồng bộ...' : 'Đồng bộ'}
              </button>
            </div>
          )}

          {/* Center Content: Switch between Layout Master and Inbound */}
          <div 
            className={currentView === 'master'
              ? 'absolute top-16 bottom-20 flex items-center justify-center transition-all duration-200'
              : 'absolute inset-0 pt-16 pb-6 overflow-y-auto scrollbar-thin transition-all duration-200 flex flex-col items-center'
            }
            style={!isMobile ? (
              currentView === 'master'
                ? {
                    left: sidebarHovered ? '468px' : '356px',
                    right: '384px'
                  }
                : {
                    paddingLeft: sidebarHovered ? '176px' : '64px',
                    paddingRight: '24px'
                  }
            ) : {
              paddingLeft: '24px',
              paddingRight: '24px'
            }}
          >
            {currentView === 'master' ? (
              renderSVG()
            ) : currentView === 'heatmap' ? (
              <HeatmapDashboard
                loading={loading}
                fetchAndUpdateData={fetchAndUpdateData}
                lastUpdate={lastUpdate}
                heatmapData={heatmapRows}
              />
            ) : currentView === 'maps' ? (
              <RouteMapDashboard />
            ) : currentView === 'kpi' ? (
              <KpiDashboard
                inboundData={inboundData}
                linehaulData={linehaulData}
                arrivalData={arrivalData}
                truckEtaData={truckEtaData}
                selectedInboundDate={selectedInboundDate}
                setSelectedInboundDate={handleInboundDateChange}
                loading={loading}
                fetchAndUpdateData={fetchAndUpdateData}
                lastUpdate={lastUpdate}
              />
            ) : (
              <InboundDashboard
                inboundData={inboundData}
                linehaulData={linehaulData}
                arrivalData={arrivalData}
                truckEtaData={truckEtaData}
                selectedInboundDate={selectedInboundDate}
                setSelectedInboundDate={handleInboundDateChange}
                loading={loading}
                fetchAndUpdateData={fetchAndUpdateData}
                lastUpdate={lastUpdate}
                lastUpdateObj={lastUpdateObj}
                kpiSummary={microKpiSummary}
                hourlyTrend={microHourlyTrend}
                ordersStatus={microOrdersStatus}
                truckEtaMicro={microTruckEta}
                originStation={microOriginStation}
              />
            )}
          </div>
        </>
      ) : ( 
        /* ── MOBILE LAYOUT ── */
        <>
          <div className="w-full h-full pt-2 pb-20 px-2 overflow-y-auto flex flex-col space-y-3">
            {activeTab === 'layout' && (
              <div className="w-full flex flex-col space-y-3 relative">
                {/* 🎯 Ultra-Premium Mobile Top Control Bar (High-Tech Glassmorphism) */}
                <div className="w-full flex flex-col gap-2 p-2.5 bg-[#0b1019]/95 backdrop-blur-xl rounded-2xl border border-white/10 shadow-[0_10px_30px_rgba(0,0,0,0.5)] sticky top-0 z-30">
                  <div className="flex gap-2 items-center">
                    <div className="relative flex-1">
                      <select value={selectedType} onChange={e => setSelectedType(e.target.value as any)}
                              className="w-full bg-[#131b2a] text-white text-[11px] font-extrabold py-2 px-3 pr-6 rounded-xl border border-white/10 outline-none appearance-none cursor-pointer focus:border-[#06b6d4] transition-all shadow-inner">
                        <option value="Outbound">⚡ Outbound</option>
                        <option value="Backlog">📦 Backlog</option>
                        <option value="Inventory">📊 Volume</option>
                      </select>
                      <div className="pointer-events-none absolute inset-y-0 right-2 flex items-center text-slate-400 text-[9px]">▼</div>
                    </div>

                    <div className="relative flex-1">
                      <select value={selectedDate} onChange={e => setSelectedDate(e.target.value)}
                              className="w-full bg-[#131b2a] text-white text-[11px] font-extrabold py-2 px-3 pr-6 rounded-xl border border-white/10 outline-none appearance-none cursor-pointer focus:border-[#06b6d4] transition-all shadow-inner">
                        {availableDates.length > 0
                          ? availableDates.map(d => <option key={d} value={d}>📅 {d}</option>)
                          : <option value="">Chưa có dữ liệu</option>}
                      </select>
                      <div className="pointer-events-none absolute inset-y-0 right-2 flex items-center text-slate-400 text-[9px]">▼</div>
                    </div>

                    <button onClick={fetchAndUpdateData} disabled={loading}
                            className="relative group overflow-hidden rounded-xl p-[1px] font-bold text-[10.5px] tracking-wider uppercase transition-all duration-300 active:scale-95 shrink-0 shadow-[0_0_15px_rgba(16,185,129,0.25)]">
                      <span className="absolute inset-0 bg-gradient-to-r from-[#10b981] via-[#06b6d4] to-[#8b5cf6] animate-pulse" />
                      <span className="relative flex items-center gap-1.5 px-3 py-2 bg-[#0d131f] rounded-[11px] text-[#B8F7E4] group-hover:bg-[#131b2c] transition-colors">
                        <RotateCw size={13} className={`text-[#10b981] ${loading ? 'animate-spin' : ''}`} />
                        <span className="font-extrabold tracking-wide">{loading ? 'TẢI...' : 'ĐỒNG BỘ'}</span>
                      </span>
                    </button>
                  </div>

                  {/* Inventory Status Chips - Flow naturally without overlapping */}
                  {selectedType === 'Inventory' && (
                    <div className="flex items-center gap-1.5 overflow-x-auto py-1 scrollbar-none"
                         style={{ scrollbarWidth: 'none', msOverflowStyle: 'none' }}>
                      <button onClick={toggleAllStatuses}
                        className={`px-2.5 py-1 rounded-full border text-[10px] font-medium transition-all duration-200 shrink-0 ${
                          selectedStatuses.length === INVENTORY_STATUSES.length
                            ? 'bg-yellow-500/10 border-yellow-500/40 text-yellow-400 font-bold'
                            : 'bg-[#121824]/40 border-white/5 text-slate-400'
                        }`}>Tất cả</button>
                      {INVENTORY_STATUSES.map(status => {
                        const isChecked = selectedStatuses.includes(status);
                        return (
                          <button key={status} onClick={() => toggleStatus(status)}
                            className={`px-2.5 py-1 rounded-full border text-[10px] font-medium transition-all duration-200 shrink-0 ${
                              isChecked
                                ? 'bg-yellow-500/10 border-yellow-500/40 text-yellow-400 font-bold'
                                : 'bg-[#121824]/40 border-white/5 text-slate-400'
                            }`}>{status}</button>
                        );
                      })}
                    </div>
                  )}
                </div>

                {/* 🎯 Mobile Telemetry Cards: METRICS & DỰ KIẾN SL LINEHAUL (Zero Overflow) */}
                <div className="w-full grid grid-cols-1 sm:grid-cols-2 gap-2 max-w-full overflow-hidden">
                  {/* Card 1: METRICS */}
                  <div className="jt-glowing-card p-2.5 shadow-lg rounded-xl w-full max-w-full overflow-hidden" style={{ background: 'rgba(255,255,255,0.04)' }}>
                    <div className="font-extrabold text-[10px] tracking-[0.14em] text-center mb-1.5 uppercase text-[#FFF4D6]" style={{ fontFamily: "'Inter', sans-serif" }}>
                      METRICS
                    </div>
                    <div className="flex justify-between items-center text-[11px] border-b border-white/5 pb-1 mb-1">
                      <span className="text-slate-300 font-semibold truncate">Tổng đơn hàng</span>
                      <span className="mono font-bold text-xs text-[#B8F7E4] shrink-0 ml-2">{totalOrders.toLocaleString()} <span className="text-[9px] text-slate-400 font-normal">Đơn</span></span>
                    </div>
                    <div className="flex justify-between items-center text-[11px]">
                      <span className="text-slate-300 font-semibold truncate">Tổng trọng lượng</span>
                      <span className="mono font-bold text-xs text-[#B8F7E4] shrink-0 ml-2">{totalWeight.toFixed(1).replace('.', ',')} <span className="text-[9px] text-slate-400 font-normal">Tấn</span></span>
                    </div>
                  </div>

                  {/* Card 2: DỰ KIẾN SL LINEHAUL */}
                  {(() => {
                    const linehaulOrders = microKpiSummary?.linehaul ?? (data['A06']?.current ?? 0);
                    const linehaulWeight = microKpiSummary?.linehaul_weight ?? (data['A06']?.weight ?? 0);
                    const fcTotal = microKpiSummary?.forecast_total && microKpiSummary.forecast_total > 0
                      ? microKpiSummary.forecast_total
                      : (totalOrders > 0 ? totalOrders : 1);
                    const pct = ((linehaulOrders / fcTotal) * 100).toFixed(1);

                    return (
                      <div className="jt-glowing-card p-2.5 shadow-lg rounded-xl w-full max-w-full overflow-hidden" style={{ background: 'rgba(255,255,255,0.04)', borderTop: '1px solid rgba(249,115,22,0.3)' }}>
                        <div className="flex justify-between items-center mb-1.5 pb-1 border-b border-white/5 gap-1">
                          <span className="text-[10px] font-extrabold uppercase text-[#f97316] truncate">🔸 Dự kiến SL LINEHAUL</span>
                          <span className="text-[9.5px] font-extrabold text-[#22d3ee] bg-[#22d3ee]/10 px-1.5 py-0.5 rounded-md border border-[#22d3ee]/30 shrink-0">
                            {linehaulOrders.toLocaleString()} Đơn
                          </span>
                        </div>
                        <div className="grid grid-cols-3 gap-1 text-center">
                          <div className="bg-white/5 p-1 rounded-md overflow-hidden">
                            <div className="text-slate-400 text-[8.5px] font-bold">HUB</div>
                            <div className="font-extrabold text-white text-[10px] truncate">BN HUB</div>
                          </div>
                          <div className="bg-white/5 p-1 rounded-md overflow-hidden">
                            <div className="text-slate-400 text-[8.5px] font-bold">T.LƯỢNG</div>
                            <div className="font-extrabold text-[#818cf8] text-[10px] truncate">{linehaulWeight.toFixed(1)}T</div>
                          </div>
                          <div className="bg-white/5 p-1 rounded-md overflow-hidden">
                            <div className="text-slate-400 text-[8.5px] font-bold">% VOL</div>
                            <div className="font-extrabold text-[#34d399] text-[10px] truncate">{pct}%</div>
                          </div>
                        </div>
                      </div>
                    );
                  })()}
                </div>

                {/* SVG Map Container */}
                <div className="relative w-full h-[550px] bg-[#02040a] rounded-xl overflow-hidden border border-white/10 shadow-2xl">
                  {/* Floating Zoom controls */}
                  <div className="mobile-fab-container">
                    <button className="mobile-fab text-base font-bold" onClick={handleZoomIn}>＋</button>
                    <button className="mobile-fab text-base font-bold" onClick={handleZoomOut}>－</button>
                    <button className="mobile-fab text-sm" onClick={handleResetZoom}>🔄</button>
                  </div>

                  {renderSVG()}
                </div>

                {/* Bottom Sheet for Mobile Chute Details */}
                <div className={`bottom-sheet ${bottomSheetOpen && hoveredRack ? 'open' : ''}`}>
                  {hoveredRack && (
                    <>
                      <div className="bottom-sheet-close" onClick={() => { setBottomSheetOpen(false); setHoveredRack(null); }}>✕</div>
                      <h4 className="disp text-[10px] tracking-[0.14em] text-[var(--accent)] mb-3 uppercase font-bold">Chi tiết ô chứa</h4>
                      <div className="grid grid-cols-2 gap-3 bg-[#101622]/60 rounded-md p-3 border border-white/5">
                        <div>
                          <div className="text-[9px] text-[var(--muted)]">Mã ô:</div>
                          <div className="mono text-[11px] font-bold text-[var(--cyan)]">{hoveredRack.areaId}</div>
                        </div>
                        <div>
                          <div className="text-[9px] text-[var(--muted)]">Tên bưu cục:</div>
                          <div className="text-[11px] font-bold text-white truncate" title={hoveredRack.name}>{hoveredRack.name}</div>
                        </div>
                        <div>
                          <div className="text-[9px] text-[var(--muted)]">Sản lượng:</div>
                          <div className="mono text-[11px] font-bold text-white">{hoveredRack.current?.toLocaleString()} / {hoveredRack.capacity}</div>
                        </div>
                        <div>
                          <div className="text-[9px] text-[var(--muted)]">Trọng lượng:</div>
                          <div className="mono text-[11px] font-bold text-white">{hoveredRack.weight?.toLocaleString()} kg</div>
                        </div>
                        <div>
                          <div className="text-[9px] text-[var(--muted)]">{displayUtilizationLabelLc}:</div>
                          <div className="mono text-[11px] font-bold" style={{color: UTILCOL[hoveredRack.bucket] || '#fff'}}>{hoveredRack.utilization}%</div>
                        </div>
                      </div>
                    </>
                  )}
                </div>
              </div>
            )}

            {activeTab === 'top10' && (
              <div className="w-full h-full overflow-y-auto px-1 pt-2">
                <div className="glass-card p-5 shadow-2xl">
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', borderBottom: '1px solid rgba(255,255,255,0.06)', paddingBottom: '12px', marginBottom: '16px' }}>
                    <h3 className="disp text-xs tracking-[0.14em] text-[var(--accent)] font-bold uppercase" style={{ margin: 0 }}>
                      {selectedType === 'Outbound' ? 'TOP 10 BƯU CỤC XUẤT HÀNG' : 'TOP 10 BƯU CỤC TỒN HÀNG'}
                    </h3>
                    <span className="badge-count sky">Top 10</span>
                  </div>
                  <div className="premium-table-wrapper">
                    <table className="premium-table">
                      <thead>
                        <tr>
                          <th style={{ width: '40px' }}>#</th>
                          <th style={{ width: '60px' }}>Mã</th>
                          <th>Bưu Cục</th>
                          <th style={{ textAlign: 'right', width: '90px' }}>{selectedType === 'Outbound' ? 'Lượng xuất' : 'Tồn'}</th>
                          <th style={{ textAlign: 'right', width: '100px' }}>T.lượng</th>
                          <th style={{ textAlign: 'right', width: '60px' }}>%</th>
                        </tr>
                      </thead>
                      <tbody>
                        {getTop10Chutes().map((chute, index) => {
                          const colors: Record<string, string> = {
                            green: '#10b981',
                            yellow: '#f59e0b',
                            orange: '#f97316',
                            red: '#ef4444',
                            darkred: '#ef4444'
                          };
                          const col = colors[chute.bucket] || '#fff';
                          return (
                            <tr key={chute.areaId}>
                              <td className="table-index">{index + 1}</td>
                              <td className="num-tabular font-bold" style={{ color: 'var(--cyan)' }}>{chute.areaId}</td>
                              <td className="table-buucuc">{chute.name}</td>
                              <td className="num-tabular" style={{ textAlign: 'right', fontWeight: 600 }}>{chute.current.toLocaleString()}</td>
                              <td className="num-tabular" style={{ textAlign: 'right', color: '#cbd5e1' }}>{Math.round(chute.weight).toLocaleString()} kg</td>
                              <td className="num-tabular" style={{ textAlign: 'right', fontWeight: 'bold', color: col }}>{chute.utilization}%</td>
                            </tr>
                          );
                        })}
                      </tbody>
                    </table>
                  </div>
                </div>
              </div>
            )}

            {activeTab === 'stats' && (
              <div className="w-full max-w-full overflow-x-hidden space-y-3 px-2 pt-2 pb-24">
                {/* Telemetry Block */}
                <div className="bg-[var(--panel)] border border-white/10 border-t-2 border-t-[var(--accent)] rounded-xl p-3.5 shadow-xl w-full max-w-full overflow-hidden">
                  <h3 className="disp text-[11px] tracking-[0.14em] pb-2.5 mb-2.5 border-b border-[var(--line)] text-[var(--accent)] font-bold uppercase truncate">TÌNH TRẠNG VẬN HÀNH</h3>
                  <div className="grid grid-cols-2 gap-2">
                    <div className="p-2.5 text-center bg-[#101622]/40 rounded-lg border border-white/5 overflow-hidden">
                      <div className="mono text-[9px] text-[var(--muted)] mb-1 font-semibold truncate">TỔNG ĐƠN HÀNG</div>
                      <div className="disp font-extrabold text-lg sm:text-xl text-[var(--cyan)] truncate">{totalOrders.toLocaleString()}</div>
                    </div>
                    <div className="p-2.5 text-center bg-[#101622]/40 rounded-lg border border-white/5 overflow-hidden">
                      <div className="mono text-[9px] text-[var(--muted)] mb-1 font-semibold truncate">TỔNG TRỌNG LƯỢNG</div>
                      <div className="disp font-extrabold text-lg sm:text-xl text-[var(--green)] truncate">
                        {Math.ceil(totalWeight).toLocaleString()} <span className="text-[10px] text-slate-400 font-normal">kg</span>
                      </div>
                    </div>
                  </div>
                </div>

                {/* Operational Stats */}
                <div className="bg-[var(--panel)] border border-white/10 border-t-2 border-t-[var(--accent)] rounded-xl p-3.5 shadow-xl w-full max-w-full overflow-hidden">
                  <h3 className="disp text-[11px] tracking-[0.14em] pb-2.5 mb-2.5 border-b border-[var(--line)] text-[var(--accent)] font-bold uppercase truncate">THỐNG KÊ CHI TIẾT</h3>
                  <div className="space-y-2.5">
                    {[
                      [displayUtilizationLabel, `${utilTotal}%`, 'var(--cyan)'],
                      ['CÒN TRỐNG', `${free}`, 'var(--green)'],
                      ['Ô ĐANG DÙNG', `${usedCells}/${CHUTE_RACKS.length}`, '#fff']
                    ].map(([label, val, col]) => (
                      <div key={label} className="flex justify-between items-center text-xs text-[var(--muted)] border-b border-[#1e2942]/50 pb-2 gap-2">
                        <span className="truncate">{label}</span>
                        <span className="mono font-bold text-sm shrink-0" style={{color: col}}>{val}</span>
                      </div>
                    ))}
                    <div className="h-1.5 rounded bg-[var(--line)] overflow-hidden">
                      <div className="h-full bg-gradient-to-r from-[var(--green)] to-[var(--cyan)] transition-all duration-1000"
                           style={{width:`${Math.min(100,Number(utilTotal))}%`}}/>
                    </div>
                  </div>
                </div>

                {/* Zone Metrics Blocks */}
                <div className="bg-[var(--panel)] border border-white/10 border-t-2 border-t-[var(--cyan)] rounded-xl p-3.5 shadow-xl w-full max-w-full overflow-hidden">
                  <h3 className="disp text-[11px] tracking-[0.14em] pb-2.5 mb-2.5 border-b border-[var(--line)] text-[var(--cyan)] font-bold uppercase truncate">THỐNG KÊ PHÂN KHU (ZONES)</h3>
                  <div className="space-y-3">
                    {[3, 2, 1].map(zoneNum => {
                      const zInfo = getZoneInfo(zoneNum);
                      const colors: Record<number, string> = {
                        1: 'var(--orange)',
                        2: 'var(--yellow)',
                        3: 'var(--green)'
                      };
                      const zColor = colors[zoneNum] || 'var(--cyan)';
                      return (
                        <div key={zoneNum} className="p-3 bg-[#101622]/40 rounded-lg border border-white/5 overflow-hidden"
                             style={{ borderColor: `${zColor}33` }}>
                          <div className="flex justify-between items-center border-b border-[#1e2942]/50 pb-2 mb-2 gap-2">
                            <span className="disp font-extrabold text-[11px] shrink-0" style={{ color: zColor }}>ZONE {zoneNum}</span>
                            <span className="mono text-[11px] font-bold shrink-0" style={{ color: zColor }}>{zInfo.ratio}% sản lượng</span>
                          </div>
                          <div className="grid grid-cols-2 gap-2 text-[10px] text-[var(--muted)]">
                            <div className="truncate">Bưu cục có hàng: <b className="text-white mono">{zInfo.activeChutesCount}/{zInfo.totalChutes}</b></div>
                            <div className="truncate">Tổng lượng đơn: <b className="text-white mono">{zInfo.zoneOrders.toLocaleString()}</b></div>
                            <div className="col-span-2 mt-1 border-t border-white/5 pt-1.5 truncate">Tổng trọng lượng: <b className="text-white mono">{zInfo.zoneWeight.toFixed(1).replace('.', ',')} Tấn</b></div>
                          </div>
                        </div>
                      );
                    })}
                  </div>
                </div>
              </div>
            )}

            {activeTab === 'inbound' && (
              <div className="w-full h-full overflow-y-auto space-y-4 px-1 pt-2 pb-6">
                <InboundDashboard
                  inboundData={inboundData}
                  linehaulData={linehaulData}
                  arrivalData={arrivalData}
                  truckEtaData={truckEtaData}
                  selectedInboundDate={selectedInboundDate}
                  setSelectedInboundDate={handleInboundDateChange}
                  loading={loading}
                  fetchAndUpdateData={fetchAndUpdateData}
                  lastUpdate={lastUpdate}
                  lastUpdateObj={lastUpdateObj}
                  kpiSummary={microKpiSummary}
                  hourlyTrend={microHourlyTrend}
                  ordersStatus={microOrdersStatus}
                  truckEtaMicro={microTruckEta}
                  originStation={microOriginStation}
                />
              </div>
            )}

            {activeTab === 'heatmap' && (
              <div className="w-full h-full overflow-y-auto space-y-4 px-1 pt-2 pb-6">
                <HeatmapDashboard
                  loading={loading}
                  fetchAndUpdateData={fetchAndUpdateData}
                  lastUpdate={lastUpdate}
                  heatmapData={heatmapRows}
                />
              </div>
            )}

            {activeTab === 'kpi' && (
              <div className="w-full h-full overflow-y-auto space-y-4 px-1 pt-2 pb-6">
                <KpiDashboard
                  inboundData={inboundData}
                  linehaulData={linehaulData}
                  arrivalData={arrivalData}
                  truckEtaData={truckEtaData}
                  selectedInboundDate={selectedInboundDate}
                  setSelectedInboundDate={handleInboundDateChange}
                  loading={loading}
                  fetchAndUpdateData={fetchAndUpdateData}
                  lastUpdate={lastUpdate}
                  lastUpdateObj={lastUpdateObj}
                />
              </div>
            )}

          </div>

          {/* Bottom Navigation Bar */}
          <div className="mobile-nav">
            <div className={`mobile-nav-item ${activeTab === 'layout' ? 'active' : ''}`} onClick={() => setActiveTab('layout')}>
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M3 9l9-7 9 7v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/><polyline points="9 22 9 12 15 12 15 22"/></svg>
              <span>Sơ đồ</span>
            </div>
            <div className={`mobile-nav-item ${activeTab === 'inbound' ? 'active' : ''}`} onClick={() => setActiveTab('inbound')}>
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><polyline points="22 12 18 12 15 21 9 3 6 12 2 12"/></svg>
              <span>Inbound</span>
            </div>
            <div className={`mobile-nav-item ${activeTab === 'heatmap' ? 'active' : ''}`} onClick={() => setActiveTab('heatmap')}>
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><rect x="3" y="4" width="18" height="18" rx="2" ry="2"/><line x1="16" y1="2" x2="16" y2="6"/><line x1="8" y1="2" x2="8" y2="6"/><line x1="3" y1="10" x2="21" y2="10"/></svg>
              <span>Heatmap</span>
            </div>
            <div className={`mobile-nav-item ${activeTab === 'top10' ? 'active' : ''}`} onClick={() => setActiveTab('top10')}>
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><circle cx="12" cy="8" r="7"/><polyline points="8.21 13.89 7 23 12 20 17 23 15.79 13.88"/></svg>
              <span>Top 10</span>
            </div>
            <div className={`mobile-nav-item ${activeTab === 'kpi' ? 'active' : ''}`} onClick={() => setActiveTab('kpi')}>
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><polyline points="23 6 13.5 15.5 8.5 10.5 1 18"/><polyline points="17 6 23 6 23 12"/></svg>
              <span>KPI</span>
            </div>
            <div className={`mobile-nav-item ${activeTab === 'stats' ? 'active' : ''}`} onClick={() => setActiveTab('stats')}>
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><line x1="18" y1="20" x2="18" y2="10"/><line x1="12" y1="20" x2="12" y2="4"/><line x1="6" y1="20" x2="6" y2="14"/></svg>
              <span>Thống kê</span>
            </div>
          </div>
        </>
      )}

      {/* ── Critical Alert Ticker ── */}
      <style>{`
        @keyframes inlineMarquee {
          0% { transform: translateX(0%); }
          100% { transform: translateX(-50%); }
        }
        .animate-inline-marquee {
          display: inline-flex !important;
          white-space: nowrap !important;
          animation: inlineMarquee 25s linear infinite !important;
        }
        .animate-inline-marquee:hover {
          animation-play-state: paused !important;
        }
      `}</style>
      <div className={`hidden md:flex absolute bottom-0 right-0 h-8 bg-[#09111c] border-t border-[#00e5ff]/30 text-white items-center z-30 mono font-bold text-[11.5px] tracking-[0.05em] overflow-hidden backdrop-blur-md shadow-[0_-4px_15px_rgba(0,0,0,0.5)] transition-all duration-200 ${
        sidebarHovered ? 'left-40' : 'left-12'
      }`}>
        <div className="bg-[#00e5ff] text-[#09111c] px-3.5 h-full flex items-center shrink-0 z-20 font-bold text-[11px] uppercase tracking-wider shadow-md">
          {currentView === 'inbound' ? '● INBOUND ALERT' : '● CRITICAL ALERT'}
        </div>
        <div className="w-full overflow-hidden relative flex items-center h-full">
          <div className="animate-inline-marquee text-emerald-400 font-bold px-4 tracking-wider flex gap-8 items-center shrink-0">
            <span className="flex gap-8 items-center">
              <span className="text-emerald-400">● {tickerText || 'HỆ THỐNG ỔN ĐỊNH — SẢN LƯỢNG TRONG GIỚI HẠN AN TOÀN'}</span>
              <span className="text-cyan-400">❖ HỆ THỐNG GIÁM SÁT SẢN LƯỢNG HCM HUB REALTIME</span>
              <span className="text-yellow-400">⚡ CẬP NHẬT TỰ ĐỘNG DỮ LIỆU TỪ POSTGRESQL & JFS API</span>
            </span>
            <span className="flex gap-8 items-center">
              <span className="text-emerald-400">● {tickerText || 'HỆ THỐNG ỔN ĐỊNH — SẢN LƯỢNG TRONG GIỚI HẠN AN TOÀN'}</span>
              <span className="text-cyan-400">❖ HỆ THỐNG GIÁM SÁT SẢN LƯỢNG HCM HUB REALTIME</span>
              <span className="text-yellow-400">⚡ CẬP NHẬT TỰ ĐỘNG DỮ LIỆU TỪ POSTGRESQL & JFS API</span>
            </span>
          </div>
        </div>
      </div>

      {/* ── Interactive Detail Modal Drawer ── */}
      {selectedDetailRack && (
        <div className="fixed inset-0 z-50 flex justify-end bg-black/70 backdrop-blur-sm transition-all" onClick={() => setSelectedDetailRack(null)}>
          <div className="w-full max-w-md bg-[#0f172a] border-l border-white/10 p-6 flex flex-col gap-6 text-white shadow-2xl relative" onClick={e => e.stopPropagation()}>
            <div className="flex items-center justify-between border-b border-white/10 pb-4">
              <div className="flex items-center gap-3">
                <div className="w-12 h-12 rounded-xl bg-[#00e5ff]/10 border border-[#00e5ff]/30 flex items-center justify-center text-[#00e5ff] font-bold mono text-xl shadow-[0_0_15px_rgba(0,229,255,0.2)]">
                  {selectedDetailRack.item.areaId}
                </div>
                <div>
                  <h2 className="font-bold text-lg text-white">{selectedDetailRack.item.name || selectedDetailRack.item.areaId}</h2>
                  <p className="text-xs text-slate-400">Phân khu Zone {selectedDetailRack.item.zone || 1} — Chi tiết ô chia chọn</p>
                </div>
              </div>
              <button onClick={() => setSelectedDetailRack(null)} className="w-8 h-8 rounded-lg bg-white/5 hover:bg-white/10 flex items-center justify-center text-slate-400 hover:text-white transition-all text-sm font-bold">
                ✕
              </button>
            </div>

            <div className="space-y-4">
              <div className="grid grid-cols-2 gap-3">
                <div className="bg-white/[0.03] border border-white/5 p-4 rounded-xl">
                  <div className="text-[10px] text-slate-400 uppercase font-bold tracking-wider mb-1">Sản lượng hiện tại</div>
                  <div className="text-2xl font-bold mono text-[#00e5ff]">
                    {selectedDetailRack.detail?.current?.toLocaleString() || 0} <span className="text-xs font-normal text-slate-400">đơn</span>
                  </div>
                </div>

                <div className="bg-white/[0.03] border border-white/5 p-4 rounded-xl">
                  <div className="text-[10px] text-slate-400 uppercase font-bold tracking-wider mb-1">Tỷ lệ lấp đầy</div>
                  <div className="text-2xl font-bold mono text-[#10b981]">
                    {selectedDetailRack.detail?.utilization || 0}%
                  </div>
                </div>
              </div>

              <div className="bg-white/[0.03] border border-white/5 p-4 rounded-xl space-y-3">
                <div className="flex justify-between items-center text-xs">
                  <span className="text-slate-400">Sức chứa tối đa:</span>
                  <span className="mono font-bold">{selectedDetailRack.detail?.capacity || 780} đơn</span>
                </div>
                <div className="flex justify-between items-center text-xs">
                  <span className="text-slate-400">Còn trống:</span>
                  <span className="mono font-bold text-[#38bdf8]">{selectedDetailRack.detail?.remaining || 0} đơn</span>
                </div>
                <div className="flex justify-between items-center text-xs">
                  <span className="text-slate-400">Tổng trọng lượng:</span>
                  <span className="mono font-bold text-[#f59e0b]">{(selectedDetailRack.detail?.weight || 0).toLocaleString()} kg</span>
                </div>
                <div className="flex justify-between items-center text-xs">
                  <span className="text-slate-400">Trạng thái vận hành:</span>
                  <span className={`px-2 py-0.5 rounded text-[10px] font-bold ${
                    (selectedDetailRack.detail?.utilization || 0) >= 95 ? 'bg-red-500/20 text-red-400 border border-red-500/30' :
                    (selectedDetailRack.detail?.utilization || 0) >= 80 ? 'bg-amber-500/20 text-amber-400 border border-amber-500/30' :
                    'bg-emerald-500/20 text-emerald-400 border border-emerald-500/30'
                  }`}>
                    {(selectedDetailRack.detail?.utilization || 0) >= 95 ? 'QUÁ TẢI (CRITICAL)' :
                     (selectedDetailRack.detail?.utilization || 0) >= 80 ? 'CẢNH BÁO (WARNING)' : 'BÌNH THƯỜNG (OK)'}
                  </span>
                </div>
              </div>

              <div className="bg-white/[0.03] border border-white/5 p-4 rounded-xl space-y-2">
                <div className="text-xs font-bold text-slate-300">Tuyến / Bưu cục kết nối:</div>
                <div className="text-sm font-semibold text-[#60a5fa]">{selectedDetailRack.item.name}</div>
                <p className="text-xs text-slate-400 leading-relaxed">
                  Đảm bảo tiến độ luồng hàng nhập & phát theo cam kết thời gian SLA vận hành HUB.
                </p>
              </div>
            </div>

            <button onClick={() => setSelectedDetailRack(null)} className="w-full py-3 bg-[#00e5ff]/10 hover:bg-[#00e5ff]/20 border border-[#00e5ff]/30 text-[#00e5ff] font-bold rounded-xl transition-all text-xs tracking-wider uppercase">
              Đóng Cửa Sổ
            </button>
          </div>
        </div>
      )}
    </div>
  );
}

