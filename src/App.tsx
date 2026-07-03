import { useState, useEffect, useMemo } from 'react';
import { 
  LayoutDashboard, 
  Activity, 
  TrendingUp, 
  Sliders, 
  RefreshCw, 
  Power,
  ListOrdered,
  Menu,
  Inbox,
  Truck
} from 'lucide-react';

// ── Rack / chute definitions (Cập nhật: Zone 3 = 23 chutes + 24 trucks, Zone 2 = 23 chutes + 23 trucks, Zone 1 = 15 chutes) ──
const ZONE3_LIST = [
  // 5 ô chutes bên phải vách ngăn (vùng xanh lá)
  { areaId: 'C01', name: 'C01 Chờ tải', zone: 3 },
  { areaId: 'C02', name: 'C02 Chờ tải', zone: 3 },
  { areaId: 'C03', name: 'C03 Chờ tải', zone: 3 },
  { areaId: 'C04', name: 'C04 Chờ tải', zone: 3 },
  { areaId: 'C05', name: 'C05 Chờ tải', zone: 3 },
  // 19 ô chutes bên trái vách ngăn (C06 -> C24, giữ nguyên bưu cục cũ của C01->C18)
  { areaId: 'C06', name: 'BD BÌNH PHƯỚC', zone: 3 }, { areaId: 'C07', name: 'SG BẢY HIỀN', zone: 3 },
  { areaId: 'C08', name: 'BD PHÚ NHUẬN', zone: 3 },   { areaId: 'C09', name: 'AG THOẠI SƠN', zone: 3 },
  { areaId: 'C10', name: 'AG TỊNH BIÊN', zone: 3 },   { areaId: 'C11', name: 'AG TÂN CHÂU', zone: 3 },
  { areaId: 'C12', name: 'AG AN PHÚ', zone: 3 },     { areaId: 'C13', name: 'VL CHỢ LÁCH', zone: 3 },
  { areaId: 'C14', name: 'SG NHÀ BÈ', zone: 3 },     { areaId: 'C15', name: 'ST PHÚ LỘC', zone: 3 },
  { areaId: 'C16', name: 'CT LONG MỸ', zone: 3 },    { areaId: 'C17', name: 'ST VĨNH CHÂU', zone: 3 },
  { areaId: 'C18', name: 'SG GÒ VẤP', zone: 3 },     { areaId: 'C19', name: 'LA BẾN LỨC', zone: 3 },
  { areaId: 'C20', name: 'SG XUÂN LỘC', zone: 3 },   { areaId: 'C21', name: 'DC NHÀ BÈ', zone: 3 },
  { areaId: 'C22', name: 'DC BÌNH HƯNG', zone: 3 },  { areaId: 'C23', name: 'DC GIA ĐỊNH', zone: 3 },
  { areaId: 'C24', name: 'C24 Dự phòng', zone: 3 }
];

const ZONE3_TRUCKS = Array.from({ length: 24 }, (_, i) => ({
  areaId: `T3-${String(24 - i).padStart(2, '0')}`,
  name: `TẢI Chờ 3-${String(24 - i).padStart(2, '0')}`,
  zone: 3
}));

const ZONE2_LIST = [
  // 5 ô chutes bên phải vách ngăn (vùng màu vàng)
  { areaId: 'A00', name: 'A00 Chờ tải', zone: 3 },
  { areaId: 'A01', name: 'A01 Chờ tải', zone: 3 },
  { areaId: 'A02', name: 'A02 Chờ tải', zone: 3 },
  { areaId: 'A03', name: 'A03 Chờ tải', zone: 3 },
  { areaId: 'A04', name: 'A04 Chờ tải', zone: 3 },
  // 18 ô chutes bên trái vách ngăn (B01 -> B18)
  { areaId: 'B01', name: 'SG XUÂN THỚI SƠN', zone: 2 }, { areaId: 'B02', name: 'SG TÂN NHỰT', zone: 2 },
  { areaId: 'B03', name: 'SG VĨNH LỘC', zone: 2 },      { areaId: 'B04', name: 'YT XUYÊN MỘC', zone: 2 },
  { areaId: 'B05', name: 'YT CHÂU ĐỨC', zone: 2 },      { areaId: 'B06', name: 'AN PHÚ ĐÔNG', zone: 2 },
  { areaId: 'B07', name: 'TÂN THỚI HIỆP', zone: 2 },    { areaId: 'B08', name: 'SG TÂN TẠO', zone: 2 },
  { areaId: 'B09', name: 'SG CỦ CHI', zone: 2 },         { areaId: 'B10', name: 'SG TÂN SƠN NHÌ', zone: 2 },
  { areaId: 'B11', name: 'SG HIỆP BÌNH', zone: 2 },      { areaId: 'B12', name: 'SG PHÚ LÂM', zone: 2 },
  { areaId: 'B13', name: 'SG AN LẠC', zone: 2 },         { areaId: 'B14', name: 'SG BÌNH TÂN', zone: 2 },
  { areaId: 'B15', name: 'SG TÂN HƯNG', zone: 2 },       { areaId: 'B16', name: 'SG ĐÔNG THẠNH', zone: 2 }
];

const ZONE2_TRUCKS = Array.from({ length: 21 }, (_, i) => ({
  areaId: `T2-${String(21 - i).padStart(2, '0')}`,
  name: `TẢI Chờ 2-${String(21 - i).padStart(2, '0')}`,
  zone: 2
}));

const ZONE1_LIST = [
  // 15 ô chutes bên trái vách ngăn (A05 -> A19, loại bỏ A03, A04 để tránh trùng lặp với Zone 2)
  { areaId: 'A05', name: 'AG LONG XUYÊN', zone: 1 },  { areaId: 'A06', name: 'AG CẦN ĐĂNG', zone: 1 },
  { areaId: 'A07', name: 'CT Ô MÔN', zone: 1 },       { areaId: 'A08', name: 'CT BÌNH THỦY', zone: 1 },
  { areaId: 'A09', name: 'CT NINH KIỀU', zone: 1 },   { areaId: 'A10', name: 'DT CAO LÃNH', zone: 1 },
  { areaId: 'A11', name: 'DT SA ĐÉC', zone: 1 },      { areaId: 'A12', name: 'TG HÒA KHÁNH', zone: 1 },
  { areaId: 'A13', name: 'VL VĨNH LONG', zone: 1 },   { areaId: 'A14', name: 'TG AN HỮU', zone: 1 },
  { areaId: 'A15', name: 'LA TÂN AN', zone: 1 },      { areaId: 'A16', name: 'TG MỸ THO', zone: 1 },
  { areaId: 'A17', name: 'TG TRUNG AN', zone: 1 },    { areaId: 'A18', name: 'VT VŨNG TÀU', zone: 1 },
  { areaId: 'A19', name: 'BN HUB', zone: 1 }
];

const ZONE1_TRUCKS = Array.from({ length: 16 }, (_, i) => ({
  areaId: `T1-${String(16 - i).padStart(2, '0')}`,
  name: `TẢI Chờ 1-${String(16 - i).padStart(2, '0')}`,
  zone: 1
}));

const CHUTE_RACKS = [...ZONE3_LIST, ...ZONE2_LIST, ...ZONE1_LIST];
const ALL_RACKS = [...CHUTE_RACKS, ...ZONE3_TRUCKS, ...ZONE2_TRUCKS, ...ZONE1_TRUCKS];

function generateMockData() {
  return ALL_RACKS.reduce((acc, curr) => {
    const util = Math.floor(Math.random() * 110);
    let bucket = 'green';
    if (util > 100) bucket = 'darkred';
    else if (util >= 95) bucket = 'red';
    else if (util >= 80) bucket = 'orange';
    else if (util >= 50) bucket = 'yellow';
    const capacity = 780;
    const current = Math.floor(capacity * (util / 100));
    acc[curr.areaId] = { current, capacity, remaining: Math.max(0, capacity - current), utilization: util, bucket, name: curr.name };
    return acc;
  }, {} as any);
}

function parseCSVLine(line: string): string[] {
  const parts: string[] = [];
  let current = '';
  let inQuotes = false;
  for (let charIndex = 0; charIndex < line.length; charIndex++) {
    const char = line[charIndex];
    if (char === '"') {
      inQuotes = !inQuotes;
    } else if (char === ',' && !inQuotes) {
      parts.push(current);
      current = '';
    } else {
      current += char;
    }
  }
  parts.push(current);
  return parts;
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

// Sheet GIDs for Google Spreadsheet
const SHEET_GIDS: Record<string, string> = {
  'Outbound':         '1650516820',
  'Backlog':          '1380336385',
  'Backlog CAP 6AM':  '1380336385',
  'Inventory':        '1359945051',
};

async function fetchInboundSheetData(sheetType: 'Forecast' | 'Dispatch' | 'Inbound' | 'Linehaul'): Promise<any[] | null> {
  try {
    const url = `https://docs.google.com/spreadsheets/d/1GMgvwa1MIEg0P102MDBcvwJPd-0wAeZh3hewmz_LBQI/gviz/tq?tqx=out:csv&sheet=${sheetType}`;
    const response = await fetch(url);
    if (!response.ok) throw new Error('Network response was not ok');
    const csvText = await response.text();
    const lines = csvText.split('\n');
    const rows: any[] = [];

    if (lines.length === 0) return [];

    const headerLine = lines[0].trim();
    const headers = parseCSVLine(headerLine).map(h => h.trim().replace(/^"|"$/g, ''));

    for (let i = 1; i < lines.length; i++) {
      const line = lines[i].trim();
      if (!line) continue;

      const parts = parseCSVLine(line).map(p => p.trim().replace(/^"|"$/g, ''));
      if (parts.length === 0) continue;

      const rowObj: Record<string, any> = {};
      headers.forEach((h, idx) => {
        if (idx < parts.length) {
          rowObj[h] = parts[idx];
        }
      });
      rows.push(rowObj);
    }
    return rows;
  } catch (error) {
    console.error(`Error fetching inbound sheet ${sheetType}:`, error);
    return null;
  }
}

async function fetchSheetData(sheetType: string = 'Outbound'): Promise<SheetRow[] | null> {
  try {
    const gid = SHEET_GIDS[sheetType] || '1650516820';
    const url = `https://docs.google.com/spreadsheets/d/1GMgvwa1MIEg0P102MDBcvwJPd-0wAeZh3hewmz_LBQI/export?format=csv&gid=${gid}`;
    const response = await fetch(url);
    if (!response.ok) throw new Error('Network response was not ok');
    const csvText = await response.text();
    const lines = csvText.split('\n');
    const rows: SheetRow[] = [];

    if (lines.length === 0) return [];

    const headerLine = lines[0].trim();
    const headers = parseCSVLine(headerLine).map(h => h.trim().replace(/^"|"$/g, ''));

    const colZone = headers.indexOf("Zone") !== -1 ? headers.indexOf("Zone") : 0;
    const colArea = headers.indexOf("AreaID") !== -1 ? headers.indexOf("AreaID") : (headers.indexOf("Area ID") !== -1 ? headers.indexOf("Area ID") : 1);
    const colName = headers.indexOf("BuuCuc") !== -1 ? headers.indexOf("BuuCuc") : (headers.indexOf("B\u01b0u c\u1ee5c") !== -1 ? headers.indexOf("B\u01b0u c\u1ee5c") : 2);
    // Inventory has an extra "Tr\u1ea1ng th\u00e1i" col at index 3, so Volume shifts to col 4
    const colVol = sheetType === 'Inventory'
      ? (headers.indexOf("Volume") !== -1 ? headers.indexOf("Volume") : 4)
      : (headers.indexOf("Volume") !== -1 ? headers.indexOf("Volume") : 3);
    const colCap = headers.indexOf("S\u1ee9c ch\u1ee9a") !== -1 ? headers.indexOf("S\u1ee9c ch\u1ee9a")
      : (headers.indexOf("Ki\u1ec7n h\u00e0ng") !== -1 ? headers.indexOf("Ki\u1ec7n h\u00e0ng")
      : (headers.indexOf("S\u1ee9c ch\u1ee9a Pallet") !== -1 ? headers.indexOf("S\u1ee9c ch\u1ee9a Pallet") : 7));
    const colDate = headers.indexOf("Ng\u00e0y") !== -1 ? headers.indexOf("Ng\u00e0y") : (headers.indexOf("Date") !== -1 ? headers.indexOf("Date") : -1);
    const colWeight = headers.indexOf("Weight") !== -1 ? headers.indexOf("Weight") : (headers.indexOf("Trọng lượng") !== -1 ? headers.indexOf("Trọng lượng") : -1);
    // Parse Trạng thái column for Inventory sheet (col index 3)
    const colStatus = sheetType === 'Inventory'
      ? (headers.indexOf("Tr\u1ea1ng th\u00e1i") !== -1 ? headers.indexOf("Tr\u1ea1ng th\u00e1i") : 3)
      : -1;

    const todayStr = new Date().toISOString().split('T')[0];

    for (let i = 1; i < lines.length; i++) {
      const line = lines[i].trim();
      if (!line) continue;

      const parts = parseCSVLine(line).map(p => p.trim().replace(/^"|"$/g, ''));
      if (parts.length === 0) continue;

      const zone    = parts[colZone] ? parts[colZone] : '';
      const areaId  = parts[colArea] ? parts[colArea] : '';
      const buuCuc  = parts[colName] ? parts[colName] : '';
      const volumeStr   = parts[colVol] ? parts[colVol].replace(/[,.]/g, '') : '';
      const weightStr   = colWeight !== -1 && parts[colWeight] ? parts[colWeight].replace(/[,.]/g, '') : '';
      const capacityStr = parts[colCap] ? parts[colCap].replace(/[,.]/g, '') : '780';
      const date    = colDate !== -1 && parts[colDate] ? parts[colDate] : todayStr;
      // Force type from which sheet we fetched
      const type = sheetType;
      // Parse status for Inventory rows
      const status = colStatus !== -1 && parts[colStatus] ? parts[colStatus].trim() : undefined;

      const volume   = volumeStr !== '' ? parseInt(volumeStr, 10) : NaN;
      const capacity = capacityStr !== '' ? parseInt(capacityStr, 10) : 780;
      const weight   = weightStr !== '' ? parseInt(weightStr, 10) : 0;

      if (areaId && zone) {
        rows.push({
          zone,
          areaId,
          buuCuc,
          volume: isNaN(volume) ? 0 : volume,
          weight: isNaN(weight) ? 0 : weight,
          capacity: isNaN(capacity) ? 780 : capacity,
          date,
          type,
          status
        });
      }
    }
    return rows;
  } catch (error) {
    console.error('Error fetching sheet data:', error);
    return null;
  }
}


const UTILCOL: any = { green:'#0c883d', yellow:'#0c883d', orange:'#0c883d', red:'#0c883d', darkred:'#0c883d' };

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

function ZoneCell({ c, d, bx, by, bw, bh, midLabelY, isHovered, onEnter, onLeave, onClick, addCenterLine, isTruck }:
  { c:any, d:any, bx:number, by:number, bw:number, bh:number, midLabelY:number,
    isHovered:boolean, onEnter:()=>void, onLeave:()=>void, onClick?:()=>void, addCenterLine?:boolean, isTruck?:boolean }) {
  const zoneColors: Record<number, string> = {
    3: 'var(--green)',
    2: 'var(--yellow)',
    1: 'var(--orange)'
  };
  const col = isTruck ? 'rgba(255,255,255,0.2)' : (zoneColors[c.zone] || '#374151');
  const fillH = (bh - 2) * Math.min(d.utilization, 110) / 110;
  return (
    <g onMouseEnter={onEnter} onMouseLeave={onLeave} onClick={onClick} className="cursor-pointer">
      <rect x={bx} y={by} width={bw} height={bh}
            fill={isTruck ? (isHovered ? 'rgba(255,255,255,0.08)' : 'rgba(255,255,255,0.02)') : col}
            fillOpacity={isTruck ? 1 : (isHovered ? 0.35 : 0.14)}
            stroke={col} strokeWidth="0.7" />
      {!isTruck && (
        <rect x={bx+1} y={by + bh - 1 - fillH} width={bw-2} height={fillH}
              fill={col} fillOpacity={0.7} />
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
            fill={isHovered ? '#fff' : (isTruck ? 'rgba(255,255,255,0.4)' : 'rgba(154,167,194,0.7)')}
            className="mono text-[5.5px] font-medium" pointerEvents="none">{c.areaId}</text>
    </g>
  );
}

export default function App() {
  const [isMobile, setIsMobile] = useState(window.innerWidth < 768);
  const [sidebarHovered, setSidebarHovered] = useState(false);
  const [currentView, setCurrentView] = useState<'master' | 'inbound'>('master');
  const [inboundData, setInboundData] = useState<any[]>([]);
  const [linehaulData, setLinehaulData] = useState<any[]>([]);
  const [selectedInboundDate, setSelectedInboundDate] = useState<string>('');
  const [showMonitor, setShowMonitor] = useState(true);
  const [showTelemetry, setShowTelemetry] = useState(true);
  const [showControls, setShowControls] = useState(true);
  const [showTop10, setShowTop10] = useState(true);
  const [activeTab, setActiveTab] = useState<'layout' | 'top10' | 'stats'>('layout');
  const [bottomSheetOpen, setBottomSheetOpen] = useState(false);
  const [data,       setData]       = useState<any>(generateMockData());
  const [utilTotal,  setUtilTotal]  = useState('0.0');
  const [free,       setFree]       = useState(0);
  const [usedCells,  setUsedCells]  = useState(0);
  const [totalOrders,setTotalOrders]= useState(0);

  const [totalWeight,setTotalWeight] = useState(0);
  const [hoveredRack,setHoveredRack]= useState<any>(null);
  const [tickerText, setTickerText] = useState('HỆ THỐNG ỔN ĐỊNH — KHÔNG CÓ CẢNH BÁO');
  const [loading,    setLoading]    = useState(false);
  const [hoveredZone,setHoveredZone] = useState<number | null>(null);

  // State variables for historic date/type filter
  const [rawSheetRows, setRawSheetRows] = useState<SheetRow[]>([]);
  const [availableDates, setAvailableDates] = useState<string[]>([]);
  const [selectedDate, setSelectedDate] = useState<string>('');
  const [selectedType, setSelectedType] = useState<'Outbound' | 'Backlog' | 'Backlog CAP 6AM' | 'Inventory'>('Outbound');
  const INVENTORY_STATUSES = ['\u0110ang tr\u00ean b\u00e3i', 'Ch\u01b0a v\u1ec1 HUB', '\u0110\u00e3 r\u1eddi HUB', '\u0110\u00e3 \u0111i\u1ec1u ph\u1ed1i nh\u00e2n vi\u00ean', '\u0110\u00e3 \u0111i\u1ec1u ph\u1ed1i b\u01b0u c\u1ee5c'];
  const [selectedStatuses, setSelectedStatuses] = useState<string[]>(['\u0110ang tr\u00ean b\u00e3i']);

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

  // Dynamic labels based on selectedType
  const displayUtilizationLabel = selectedType === 'Outbound' ? 'TỈ LỆ OUTBOUND' : 'TỈ LỆ LẤP ĐẦY';
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

    [1, 2, 3].forEach(z => {
      const s = stats[z];
      if (selectedType === 'Outbound') {
        s.fillRate = totalOrdersOfSelectedType > 0 ? ((s.current / totalOrdersOfSelectedType) * 100).toFixed(2) : '0.00';
      } else {
        s.fillRate = s.capacity > 0 ? Math.round((s.current / s.capacity) * 100) : 0;
      }
    });

    return stats;
  }, [data, selectedType]);

  // Fetch sheet records directly from Google Sheets (all 3 tabs in parallel)
  const fetchAndUpdateData = async () => {
    setLoading(true);
    const [
      outboundRows, backlogRows, inventoryRows,
      ibRows, lhRows
    ] = await Promise.all([
      fetchSheetData('Outbound'),
      fetchSheetData('Backlog'),
      fetchSheetData('Inventory'),
      fetchInboundSheetData('Inbound'),
      fetchInboundSheetData('Linehaul'),
    ]);

    setInboundData(ibRows ?? []);
    setLinehaulData(lhRows ?? []);

    if (ibRows && ibRows.length > 0) {
      const ibDates = Array.from(new Set(ibRows.map(r => r['Ngày vận hành']).filter(Boolean))) as string[];
      ibDates.sort((a, b) => b.localeCompare(a));
      if (ibDates.length > 0) {
        setSelectedInboundDate(prev => {
          if (prev && ibDates.includes(prev)) return prev;
          return ibDates[0];
        });
      }
    }

    const combined: SheetRow[] = [
      ...(outboundRows ?? []),
      ...(backlogRows  ?? []),
      ...(inventoryRows ?? []),
    ];

    if (combined.length > 0) {
      setRawSheetRows(combined);

      // Extract unique dates from all rows (Outbound, Backlog, Inventory), sorted descending
      const dates = Array.from(new Set(combined.map(r => r.date).filter(Boolean))) as string[];
      dates.sort((a, b) => b.localeCompare(a));
      const recentDates = dates.slice(0, 7);
      setAvailableDates(recentDates);

      if (recentDates.length > 0) {
        setSelectedDate(prev => {
          if (prev && recentDates.includes(prev)) return prev;
          return recentDates[0];
        });
      }
    } else {
      console.warn('Fetched sheet data is empty or null.');
    }
    setLoading(false);
  };

  // Derived state/Filtering effect
  useEffect(() => {
    if (rawSheetRows.length === 0) return;

    // Create lookup maps for both Backlog and the selectedType for the selectedDate
    const selectedMap: Record<string, SheetRow> = {};
    const backlogMap: Record<string, SheetRow> = {};
    // For Inventory: accumulate volumes per areaId across selected statuses
    const inventoryMap: Record<string, { volume: number; weight: number; capacity: number; buuCuc: string }> = {};

    rawSheetRows.forEach(row => {
      if (row.date === selectedDate) {
        const key = `${row.zone}_${row.areaId}`;
        if (row.type === selectedType && selectedType !== 'Inventory') {
          selectedMap[key] = row;
        }
        if (row.type === 'Inventory' && selectedType === 'Inventory') {
          // Only sum volumes for the user-selected statuses
          if (!row.status || selectedStatuses.includes(row.status)) {
            if (!inventoryMap[key]) {
              inventoryMap[key] = { volume: 0, weight: 0, capacity: row.capacity, buuCuc: row.buuCuc };
            }
            inventoryMap[key].volume += row.volume;
            inventoryMap[key].weight += row.weight;
          }
        }
        if (row.type === 'Backlog') {
          backlogMap[key] = row;
        }
      }
    });

    // Update static lists (prefer inventoryMap > selectedMap > backlogMap for names)
    const updateListName = (list: any[]) => {
      list.forEach(item => {
        const key = `${item.zone}_${item.areaId}`;
        const invEntry = inventoryMap[key];
        const activeItem = selectedMap[key] || backlogMap[key];
        const name = invEntry?.buuCuc || activeItem?.buuCuc;
        if (name) {
          item.name = name;
        } else {
          item.name = `${item.areaId} Dự phòng`;
        }
      });
    };
    updateListName(ZONE3_LIST);
    updateListName(ZONE2_LIST);
    updateListName(ZONE1_LIST);

    // Recompute visual data for ALL_RACKS
    const newData = ALL_RACKS.reduce((acc, curr: any) => {
      let capacity = 780;
      let current = 0;
      let weight = 0;
      let util = 0;
      let isMocked = rawSheetRows.length === 0;
      let backlogCurrent = 0;

      const isTruck = curr.areaId.startsWith('T');
      const key = curr.zone ? `${curr.zone}_${curr.areaId}` : null;

      if (key) {
        const item = selectedType === 'Inventory' ? null : selectedMap[key];
        const blItem = backlogMap[key];
        const invEntry = inventoryMap[key];

        if (selectedType === 'Inventory' && invEntry) {
          capacity = invEntry.capacity || 780;
          current = invEntry.volume;
          weight = invEntry.weight || 0;
          isMocked = false;
          util = Math.floor((current / capacity) * 100);
        } else if (item) {
          capacity = item.capacity;
          if (item.volume !== -1) {
            current = item.volume;
            weight = item.weight || 0;
            isMocked = false;
          }
        }

        if (blItem && blItem.volume !== -1) {
          backlogCurrent = blItem.volume;
          if (selectedType === 'Backlog') {
            weight = blItem.weight || 0;
          }
        }

        // Calculate utilization based on capacity for all modes
        if (!isMocked) {
          util = Math.floor((current / capacity) * 100);
        }
      }

      if (isMocked) {
        if (!isTruck) {
          util = Math.floor(Math.random() * 110);
          current = Math.floor(capacity * (util / 100));
          weight = Math.floor(current * 4.5);
          backlogCurrent = Math.floor(current * 0.3);
        }
      }

      if (curr.areaId === 'A19') {
        capacity = 1400;
        if (!isMocked) {
          util = Math.floor((current / capacity) * 100);
        }
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

  useEffect(() => {
    fetchAndUpdateData();
    const handleResize = () => {
      setIsMobile(window.innerWidth < 768);
    };
    window.addEventListener('resize', handleResize);
    return () => window.removeEventListener('resize', handleResize);
  }, []);

  useEffect(() => {
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
    
    if (selectedType === 'Outbound') {
      const denominator = tCur + tBacklog;
      setUtilTotal((denominator ? (tCur / denominator) * 100 : 0).toFixed(1));
    } else {
      setUtilTotal((tCap ? (tCur/tCap)*100 : 0).toFixed(1));
    }
    
    setFree(tRem); setUsedCells(tUsed); setTotalOrders(tCur); setTotalWeight(tWeight);
    
    const label = selectedType === 'Outbound' ? 'TỈ LỆ OUTBOUND' : 'LẤP ĐẦY';
    const rate = selectedType === 'Outbound'
      ? (tCur + tBacklog ? (tCur / (tCur + tBacklog)) * 100 : 0)
      : (tCap ? (tCur / tCap) * 100 : 0);
      
    setTickerText(alerts.length > 0
      ? alerts.join(' // ') + ' // ' + alerts.join(' // ')
      : `HỆ THỐNG ỔN ĐỊNH — KHÔNG CÓ CẢNH BÁO // TỔNG ${tCur} ĐƠN HÀNG // ${label} ${rate.toFixed(1)}%`
    );
  }, [data, selectedType]);

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

          <text x={A23_X+4} y={93} fill="rgba(141,160,196,0.6)" className="mono text-[6px]">Lối 6m</text>
          <text x={A23_X+4} y={247} fill="rgba(141,160,196,0.6)" className="mono text-[6px]">Lối 6m</text>
          <text x={A23_X+4} y={405} fill="rgba(141,160,196,0.6)" className="mono text-[6px]">Lối 6m</text>

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
            {ZONE3_LIST.map((c, i) => {
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
                            if (isMobile) setBottomSheetOpen(true);
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
            {/* Zone 3 Chutes Left border (bao quanh C06->C24) */}
            <rect x={110} y={118} width={532} height={Z_H} rx="2"
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
            {/* Zone 2 Trucks border (bao quanh T2-01->T2-21) */}
            <rect x={194} y={280} width={588} height={Z_H} rx="2"
                  {...getZoneBorderProps(2, '--yellow')}/>
          </g>

          <line x1={(A23_X + NS_X)/2} y1={EW_Y+EW_H/2} x2={(A23_X + NS_X)/2} y2={EW_Y+3}
                fill="none" stroke="rgba(234,179,8,0.45)" strokeWidth="1.2" markerEnd="url(#arrow)"/>
          <line x1={(A23_X + NS_X)/2} y1={EW_Y+EW_H/2} x2={(A23_X + NS_X)/2} y2={EW_Y+EW_H-3}
                fill="none" stroke="rgba(234,179,8,0.45)" strokeWidth="1.2" markerEnd="url(#arrow)"/>
          <text x={(A23_X + NS_X)/2 + 20} y={EW_Y+EW_H/2+2} textAnchor="middle"
                fill="rgba(234,179,8,0.65)" className="mono text-[5.5px] font-bold">XE TẢI CHỤM ĐẦU</text>

          <g>
            {ZONE1_LIST.filter(c => c.areaId !== 'A19').map((c, i) => {
              const d = data[c.areaId]; if (!d) return null;
              const bx = 612 - i * TR_BAY_W;
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
            <rect x={248} y={Z1_Y} width={392} height={Z_H} rx="2"
                  {...getZoneBorderProps(1, '--orange')}/>
            <text x={248} y={Z1_Y-6} fill="rgba(234, 67, 53, 0.75)"
                  className="mono text-[6.5px] font-bold tracking-wide">KHU CHỜ XUẤT TẢI (ZONE 1)</text>
          </g>
 
          {/* Render A19 (BN HUB) separately at A1-A2 with double cell width */}
          <g>
            {(() => {
              const c = ZONE1_LIST.find(item => item.areaId === 'A19');
              if (!c) return null;
              const d = data[c.areaId];
              if (!d) return null;
              const bx = 181;
              const by = Z1_Y;
              const bw = 56; // 2 cells wide
              const isHubHovered = hoveredRack?.areaId === 'A19';
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
                  <text x={bx} y={by-6} fill="rgba(234, 67, 53, 0.75)"
                        className="mono text-[6.5px] font-bold tracking-wide">BN HUB</text>
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
            <text x={181} y={632} fill="rgba(234, 67, 53, 0.75)"
                  className="mono text-[6.5px] font-bold tracking-wide">BÃI CHỜ XE TẢI (ZONE 1) - QUAY ĐẦU HƯỚNG RA</text>
          </g>

          <g>
            <text x={(IB_XL1+IB_XL2+IB_LW)/2} y={IB_Y-6} textAnchor="middle"
                  fill="var(--inbound)" className="disp text-[7.5px] font-bold tracking-wider">
              INBOUND SORT L1
            </text>

            {[IB_XL1, IB_XL2].map((lx, li) => {
              return (
                <g key={li}>
                  <rect x={lx} y={IB_Y} width={IB_LW} height={IB_H}
                        rx="2" fill="rgba(96,165,250,0.05)"
                        stroke="var(--inbound)" strokeWidth="1.1" strokeDasharray="3 2"/>

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
              <g key={g.id} className="cursor-pointer hover:opacity-80">
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

          {/* ── Footer note ── */}
          <text x={(WL+WR)/2} y={650} textAnchor="middle"
                fill="var(--muted)" className="font-sans text-[7.5px] tracking-wide">
            A1–A12: Cổng xuất (Outbound) | A13–A18: Cổng nhập hàng (Inbound)
          </text>
          </g>
        </svg>
    );
  };

  return (
    <div className="w-full h-full relative font-sans text-white bg-[#09111C]">
      <div className={`absolute top-0 right-0 h-12 flex items-center justify-between px-6 z-20 transition-all duration-300 ${
        isMobile ? 'left-0' : 'left-16'
      }`}
           style={{background:'linear-gradient(180deg,rgba(9,17,28,.95),rgba(9,17,28,0))'}}>
        <div className="flex items-center gap-3 select-none">
          {/* Logo J&T Cargo */}
          <svg width="120" height="30" viewBox="0 0 135 50" fill="none" xmlns="http://www.w3.org/2000/svg" className="h-8 w-auto">
            <rect width="135" height="50" rx="6" fill="#006a38" />
            <g transform="skewX(-16) translate(6, 2)">
              <path d="M 28,10 H 20 V 32 H 5 V 37 H 28 Z" fill="#ffffff" />
              <text x="29" y="33" fill="#ffffff" fontSize="20" fontWeight="950" fontFamily="'Arial', sans-serif">{"&"}</text>
              <rect x="52" y="15" width="8" height="22" fill="#ffffff" />
              <rect x="40" y="10" width="32" height="5" fill="#ffffff" />
              <rect x="72" y="10" width="16" height="1.4" fill="#ffffff" />
              <rect x="72" y="11.8" width="11" height="1.4" fill="#ffffff" />
              <rect x="72" y="13.6" width="6" height="1.4" fill="#ffffff" />
              <text x="76" y="36" fill="#ffffff" fontSize="18" fontWeight="bold" fontFamily="'Montserrat', 'Arial', sans-serif">Cargo</text>
            </g>
          </svg>
          <div className="h-5 w-px bg-white/20" />
          <div className="disp font-extrabold text-sm tracking-[0.18em] text-white/90"
               style={{textShadow:'0 0 12px rgba(255,255,255,0.1)'}}>HCM HUB</div>
        </div>
                {!isMobile ? (
          <div className="flex items-center gap-4">
            <div className="mono text-[10px] text-slate-400 flex items-center gap-1.5 bg-[#121824]/60 border border-white/5 rounded-full px-3 py-1">
              <span className="w-1.5 h-1.5 rounded-full bg-emerald-500 animate-pulse-slow"></span>
              SYS: <b className="text-emerald-400">ONLINE</b>
            </div>
            <div className="mono text-[10px] text-slate-400 bg-[#121824]/60 border border-white/5 rounded-full px-3 py-1">
              ZONE: LAT 10.823 • LONG 106.63
            </div>
          </div>
        ) : null}
      </div>

      {!isMobile ? (
        /* ── DESKTOP LAYOUT ── */
        <>
          {/* Sidebar Menu */}
          <div 
            onMouseEnter={() => setSidebarHovered(true)}
            onMouseLeave={() => setSidebarHovered(false)}
            className={`fixed top-0 left-0 h-full z-40 flex flex-col bg-gradient-to-b from-[#09111C] to-[#111827] border-r border-white/[0.06] transition-all duration-180 shadow-2xl ${
              sidebarHovered ? 'w-60' : 'w-16'
            }`}
          >
            {/* Sidebar Header */}
            <div className={`flex items-center p-3 border-b border-white/[0.06] h-12 ${
              sidebarHovered ? 'justify-between px-4' : 'justify-center'
            }`}>
              {sidebarHovered ? (
                <span className="text-[10px] text-slate-500 font-bold tracking-[0.08em] uppercase select-none">Danh mục giám sát</span>
              ) : (
                <Menu size={16} className="text-slate-400" />
              )}
            </div>

            {/* Menu Items */}
            <div className="flex-1 py-4 space-y-4 px-3 overflow-y-auto scrollbar-none" style={{ scrollbarWidth: 'none' }}>
              
              {/* Group 1: DASHBOARD VIEWS */}
              <div className="space-y-1">
                {sidebarHovered && (
                  <div className="px-3 text-[11px] text-[#94A3B8] font-bold tracking-[0.08em] uppercase mb-2.5 select-none">
                    Dashboard
                  </div>
                )}
                {[
                  { id: 'master', label: 'Layout Master', desc: 'Toàn bộ thông tin tổng thể', icon: LayoutDashboard, color: '#4F8CFF', active: currentView === 'master', onClick: () => setCurrentView('master') },
                  { id: 'inbound', label: 'Inbound', desc: 'Thống kê chi tiết luồng nhập', icon: Inbox, color: '#4F8CFF', active: currentView === 'inbound', onClick: () => setCurrentView('inbound') },
                ].map(item => {
                  const Icon = item.icon;
                  return (
                    <button
                      key={item.id}
                      onClick={item.onClick}
                      className={`w-full flex items-center gap-4 px-3 py-2.5 rounded-2xl text-left transition-all duration-180 group relative ${
                        item.active 
                          ? 'text-white bg-[#2d466e]/30' 
                          : 'text-[#94A3B8] hover:text-white hover:bg-white/[0.02]'
                      }`}
                      style={item.active ? { 
                        boxShadow: `0 0 8px ${item.color}08`
                      } : {}}
                    >
                      {item.active && (
                        <div 
                          className="absolute left-0 top-3.5 bottom-3.5 w-[3px] rounded-r"
                          style={{ backgroundColor: item.color }}
                        />
                      )}
                      <div 
                        className="w-10 h-10 rounded-xl flex items-center justify-center shrink-0 transition-all duration-180 group-hover:scale-105"
                        style={{ 
                          backgroundColor: 'rgba(255,255,255,0.03)',
                          border: '1px solid rgba(255,255,255,0.05)',
                          color: item.active ? item.color : '#94A3B8',
                          boxShadow: item.active ? `0 0 12px ${item.color}40` : 'none'
                        }}
                      >
                        <Icon 
                          size={18} 
                          strokeWidth={2}
                        />
                      </div>
                      {sidebarHovered && (
                        <div className="flex flex-col select-none">
                          <span className="text-base font-semibold leading-normal tracking-wide">{item.label}</span>
                          <span className="text-xs text-[#94A3B8] mt-1 font-normal leading-relaxed">{item.desc}</span>
                        </div>
                      )}
                      {!sidebarHovered && (
                        <div className="absolute left-16 bg-[#0a0e14] text-white text-[9.5px] py-1 px-2 rounded border border-white/10 opacity-0 pointer-events-none group-hover:opacity-100 transition-opacity duration-180 whitespace-nowrap z-50 shadow-xl">
                          {item.label}
                        </div>
                      )}
                    </button>
                  );
                })}
              </div>

              {/* Group 2: VIEW CONTROLS (Only visible for Master Layout to toggle widgets) */}
              {currentView === 'master' && (
                <div className="space-y-1 pt-4 border-t border-white/[0.06]">
                  {sidebarHovered && (
                    <div className="px-3 text-[11px] text-[#94A3B8] font-bold tracking-[0.08em] uppercase mb-2.5 select-none">
                      Tiện ích / Panel
                    </div>
                  )}
                  {[
                    { id: 'monitor', label: 'Giám sát phân khu', desc: 'Operational Monitor', icon: Activity, color: '#22C55E', active: showMonitor, onClick: () => setShowMonitor(!showMonitor) },
                    { id: 'telemetry', label: 'Thông số kho', desc: 'Real-time Telemetry', icon: TrendingUp, color: '#F59E0B', active: showTelemetry, onClick: () => setShowTelemetry(!showTelemetry) },
                    { id: 'controls', label: 'Bộ lọc dữ liệu', desc: 'Control Center', icon: Sliders, color: '#22D3EE', active: showControls, onClick: () => setShowControls(!showControls) },
                    { id: 'top10', label: 'Bảng xếp hạng', desc: 'Top 10 bưu cục', icon: ListOrdered, color: '#8B5CF6', active: showTop10, onClick: () => setShowTop10(!showTop10) },
                  ].map(item => {
                    const Icon = item.icon;
                    return (
                      <button
                        key={item.id}
                        onClick={item.onClick}
                        className={`w-full flex items-center gap-4 px-3 py-2.5 rounded-2xl text-left transition-all duration-180 group relative ${
                          item.active 
                            ? 'text-white bg-[#2d466e]/30' 
                            : 'text-[#94A3B8] hover:text-white hover:bg-white/[0.02]'
                        }`}
                        style={item.active ? { 
                          boxShadow: `0 0 8px ${item.color}08`
                        } : {}}
                      >
                        {item.active && (
                          <div 
                            className="absolute left-0 top-3.5 bottom-3.5 w-[3px] rounded-r"
                            style={{ backgroundColor: item.color }}
                          />
                        )}
                        <div 
                          className="w-10 h-10 rounded-xl flex items-center justify-center shrink-0 transition-all duration-180 group-hover:scale-105"
                          style={{ 
                            backgroundColor: 'rgba(255,255,255,0.03)',
                            border: '1px solid rgba(255,255,255,0.05)',
                            color: item.active ? item.color : '#94A3B8',
                            boxShadow: item.active ? `0 0 12px ${item.color}40` : 'none'
                          }}
                        >
                          <Icon 
                            size={18} 
                            strokeWidth={2}
                          />
                        </div>
                        {sidebarHovered && (
                          <div className="flex flex-col select-none">
                            <span className="text-base font-semibold leading-normal tracking-wide">{item.label}</span>
                            <span className="text-xs text-[#94A3B8] mt-1 font-normal leading-relaxed">{item.desc}</span>
                          </div>
                        )}
                        {!sidebarHovered && (
                          <div className="absolute left-16 bg-[#0a0e14] text-white text-[9.5px] py-1 px-2 rounded border border-white/10 opacity-0 pointer-events-none group-hover:opacity-100 transition-opacity duration-180 whitespace-nowrap z-50 shadow-xl">
                            {item.label}
                          </div>
                        )}
                      </button>
                    );
                  })}
                </div>
              )}

            </div>

            {/* Bottom Actions */}
            <div className="p-3 border-t border-white/[0.06] space-y-2">
              {sidebarHovered && (
                <div className="px-2 py-1 rounded bg-[#101622]/40 border border-white/5 flex items-center justify-between select-none">
                  <span className="text-[8.5px] font-mono text-slate-500">SYS STATUS</span>
                  <div className="flex items-center gap-1">
                    <span className="w-1 h-1 rounded-full bg-emerald-500 animate-pulse"></span>
                    <span className="text-[8.5px] font-mono text-emerald-400 font-bold">ONLINE</span>
                  </div>
                </div>
              )}
              <div className="flex gap-2">
                <button 
                  onClick={fetchAndUpdateData}
                  disabled={loading}
                  className={`flex-1 flex items-center justify-center gap-2 py-1.5 rounded-lg border text-[9.5px] font-bold cursor-pointer transition-colors duration-200 ${
                    loading 
                      ? 'bg-slate-800 border-white/5 text-slate-500' 
                      : 'bg-[#101622]/60 border-white/10 text-slate-300 hover:bg-white/5 hover:text-white'
                  }`}
                  title="Đồng bộ Google Sheets"
                >
                  <RefreshCw size={10} className={loading ? 'animate-spin' : ''} />
                  {sidebarHovered && (loading ? 'Đang đồng bộ...' : 'Đồng bộ')}
                </button>
                <button 
                  onClick={() => {
                    const nextVal = !(showMonitor && showTelemetry && showControls && showTop10);
                    setShowMonitor(nextVal);
                    setShowTelemetry(nextVal);
                    setShowControls(nextVal);
                    setShowTop10(nextVal);
                  }}
                  className="p-1.5 rounded-lg border border-white/10 bg-[#101622]/60 text-slate-400 hover:bg-white/5 hover:text-white cursor-pointer transition-colors"
                  title="Minimal Mode (Ẩn/Hiện tất cả)"
                >
                  <Power size={10} />
                </button>
              </div>
            </div>
          </div>

          {/* Left Column: Stacked panels (w-80) */}
          {currentView === 'master' && (
            <div className="absolute z-20 top-16 left-[80px] w-80 flex flex-col gap-4 max-h-[calc(100vh-100px)] overflow-y-auto pr-2 pb-6 scrollbar-thin transition-all duration-300">
              
              {/* 1. OPERATIONAL MONITOR & ZONE METRICS */}
              {showMonitor && (
                <div className="bg-[var(--panel)] border border-white/10 border-t-2 border-t-[var(--accent)] rounded-lg backdrop-blur-md shadow-2xl p-4 shrink-0">
              <h3 className="disp text-xs tracking-[0.14em] pb-3 mb-3 border-b border-[var(--line)] text-[var(--accent)]">OPERATIONAL MONITOR</h3>
              <div className="space-y-3">
                {[
                  [displayUtilizationLabel, `${utilTotal}%`, 'var(--cyan)'],
                  ['CÒN TRỐNG', `${free}`, 'var(--green)'],
                  ['Ô ĐANG DÙNG', `${usedCells}/${CHUTE_RACKS.length}`, '#fff']
                ].map(([label, val, col]) => (
                  <div key={label} className="flex justify-between items-center text-[13px] text-[var(--muted)] border-b border-[#1e2942]/50 pb-2">
                    <span>{label}</span>
                    <span className="mono font-bold text-[15px]" style={{color: col}}>{val}</span>
                  </div>
                ))}
                <div className="h-1.5 rounded bg-[var(--line)] overflow-hidden">
                  <div className="h-full bg-gradient-to-r from-[var(--green)] to-[var(--cyan)] transition-all duration-1000"
                       style={{width:`${Math.min(100,Number(utilTotal))}%`}}/>
                </div>
              </div>

              {/* Zone metrics section */}
              <div className="mt-5 pt-4 border-t border-[var(--line)]">
                <h4 className="disp text-[10px] tracking-[0.12em] text-[var(--muted)] mb-3">ZONE METRICS (CHI TIẾT PHÂN KHU)</h4>
                <div className="space-y-3">
                  {[
                    { id: 3, name: 'ZONE 3 CHUTES (A00-A04)', color: 'var(--green)' },
                    { id: 2, name: 'ZONE 2 CHUTES (A05-A11)', color: 'var(--yellow)' },
                    { id: 1, name: 'ZONE 1 CHUTES (A12-A19)', color: 'var(--orange)' }
                  ].map(zone => {
                    const stats = zoneStats[zone.id];
                    const isHovered = hoveredZone === zone.id;
                    return (
                      <div 
                        key={zone.id} 
                        className={`p-2.5 rounded-md border transition-all duration-300 cursor-pointer ${
                          isHovered 
                            ? 'bg-[#101622]/90 border-white/20 shadow-[0_0_12px_rgba(255,255,255,0.05)]' 
                            : 'bg-[#101622]/40 border-white/5 hover:border-white/10'
                        }`}
                        style={isHovered ? { borderColor: zone.color, boxShadow: `0 0 10px ${zone.color}22` } : {}}
                        onMouseEnter={() => setHoveredZone(zone.id)}
                        onMouseLeave={() => setHoveredZone(null)}
                      >
                        <div className="flex justify-between items-start mb-1">
                          <span className="font-bold text-[10px] tracking-wide max-w-[170px]" style={{ color: zone.color }}>
                            {zone.name}
                          </span>
                          <span className="mono text-[11px] font-bold text-white flex flex-col items-end shrink-0">
                            <span>{stats.current.toLocaleString()} đơn</span>
                            <span className="text-[9.5px] text-slate-400 font-medium mt-0.5">{stats.weight.toLocaleString()} kg</span>
                          </span>
                        </div>
                        <div className="flex justify-between items-center text-[10px] text-[var(--muted)] mb-1.5 mt-2">
                          <span>{displayUtilizationLabelLc}</span>
                          <span className="mono font-bold text-white">{stats.fillRate}%</span>
                        </div>
                        <div className="h-1 rounded bg-[var(--line)] overflow-hidden">
                          <div className="h-full transition-all duration-500"
                               style={{ 
                                 width: `${Math.min(100, Number(stats.fillRate))}%`,
                                 backgroundColor: zone.color
                               }}/>
                        </div>
                      </div>
                    );
                  })}
                </div>
              </div>

              {/* Chi tiết ô chứa (nếu có hover) */}
              <div className="mt-5 pt-4 border-t border-[var(--line)]">
                <h4 className="disp text-[10px] tracking-[0.12em] text-[var(--muted)] mb-3">CHI TIẾT Ô CHỨA</h4>
                {hoveredRack ? (
                  <div className="space-y-2 bg-[#101622]/60 rounded-md p-3 border border-white/5">
                    {[
                      ['Mã ô', hoveredRack.areaId, 'var(--cyan)'],
                      ['Tên', hoveredRack.name, '#fff'],
                      ['Số lượng', `${hoveredRack.current}/${hoveredRack.capacity} Đơn hàng`, '#fff'],
                      ['Trọng lượng', `${(hoveredRack.weight || 0).toLocaleString()} kg`, '#fff'],
                      [displayUtilizationLabelLc, `${hoveredRack.utilization}%`, UTILCOL[hoveredRack.bucket]]
                    ].map(([k,v,c]) => (
                      <div key={k} className="flex justify-between">
                        <span className="text-[11px] text-[var(--muted)]">{k}:</span>
                        <span className="mono text-[11px] font-bold truncate max-w-[150px]" style={{color:c}}>{v}</span>
                      </div>
                    ))}
                  </div>
                ) : (
                  <div className="text-center py-6 text-[11px] text-[var(--muted)] border border-dashed border-[var(--line)] rounded-md">
                    Rê chuột vào ô để xem thông tin chi tiết
                  </div>
                )}
              </div>
            </div>
            )}

            {/* 2. REAL-TIME TELEMETRY */}
            {showTelemetry && (
              <div className="bg-[var(--panel)] border border-white/10 border-t-2 border-t-[var(--accent)] rounded-lg backdrop-blur-md shadow-2xl p-4 shrink-0 w-full">
              <h3 className="disp text-xs tracking-[0.14em] pb-3 mb-2 border-b border-[var(--line)] text-[var(--accent)]">REAL-TIME TELEMETRY</h3>
              <div className="space-y-4">
                <div className="p-3 text-center border-b border-[var(--line)] bg-[#101622]/30 rounded-md">
                  <div className="mono text-[10px] tracking-[0.12em] text-[var(--muted)] mb-1">TỔNG ĐƠN HÀNG</div>
                  <div className="disp font-extrabold text-3xl text-[var(--cyan)]">{totalOrders.toLocaleString()}</div>
                  <div className="mono text-[9px] tracking-[0.1em] text-[var(--muted)] mt-1">ĐƠN HÀNG / KHO</div>
                </div>
                <div className="p-3 text-center bg-[#101622]/30 rounded-md">
                  <div className="mono text-[10px] tracking-[0.12em] text-[var(--muted)] mb-1">TỔNG TRỌNG LƯỢNG</div>
                  <div className="disp font-extrabold text-2xl text-[var(--green)]">
                    {totalWeight.toLocaleString()} kg
                  </div>
                  <div className="mono text-[9px] tracking-[0.1em] text-[var(--muted)] mt-1">TRỌNG LƯỢNG KHO</div>
                </div>
              </div>
            </div>
              )}
            </div>
          )}

          {/* Right Column: Control Center & Top 10 Racks (w-90) */}
          {currentView === 'master' && (
            <div className="absolute z-20 top-16 right-6 w-90 flex flex-col gap-4 max-h-[calc(100vh-210px)] overflow-y-auto pr-2 pb-6 scrollbar-thin">
              {/* A. Control Center Panel */}
              {showControls && (
                <div className="bg-[var(--panel)] border border-white/10 border-t-2 border-t-[var(--accent)] rounded-lg backdrop-blur-md shadow-2xl p-4 shrink-0">
              <h3 className="disp text-xs tracking-[0.14em] pb-3 mb-4 border-b border-[var(--line)] text-[var(--accent)]">CONTROL CENTER</h3>
              
              <div className="space-y-4">
                {/* 1. LOẠI (Type Selector) - Segmented Control */}
                <div className="space-y-2">
                  <div className="mono text-[9.5px] tracking-[0.1em] text-slate-400">LOẠI DỮ LIỆU</div>
                  <div className="flex bg-[#0a0e14]/90 border border-white/10 rounded-full p-1 w-full">
                    {(['Outbound', 'Backlog', 'Inventory'] as const).map(type => {
                      const isActive = selectedType === type;
                      const labelMap = { Outbound: 'Outbound', Backlog: 'Backlog', Inventory: 'Volume' };
                      return (
                        <button
                          key={type}
                          onClick={() => setSelectedType(type)}
                          className={`flex-1 text-center py-1.5 rounded-full text-[11px] font-bold transition-all duration-300 relative z-10 ${
                            isActive
                              ? 'text-white bg-[var(--accent)] shadow-[0_2px_8px_rgba(255,106,43,0.3)]'
                              : 'text-slate-400 hover:text-slate-200'
                          }`}
                        >
                          {labelMap[type]}
                        </button>
                      );
                    })}
                  </div>
                </div>

                {/* 2. NGÀY (Date Selector) - Scrollable Pill Group */}
                <div className="space-y-2">
                  <div className="mono text-[9.5px] tracking-[0.1em] text-slate-400">NGÀY BÁO CÁO</div>
                  <div className="flex gap-1.5 overflow-x-auto py-1 scrollbar-none" style={{ scrollbarWidth: 'none', msOverflowStyle: 'none' }}>
                    {availableDates.slice(0, 7).map(d => {
                      const isActive = selectedDate === d;
                      return (
                        <button
                          key={d}
                          onClick={() => setSelectedDate(d)}
                          className={`px-3 py-1.5 rounded-full text-[10.5px] font-bold border transition-all duration-250 shrink-0 ${
                            isActive
                              ? 'bg-[#1e2942]/60 border-[var(--cyan)] text-[var(--cyan)] shadow-[0_0_8px_rgba(34,211,238,0.15)]'
                              : 'bg-[#101622]/40 border-white/5 text-slate-400 hover:border-slate-700/80 hover:text-slate-200'
                          }`}
                        >
                          {d}
                        </button>
                      );
                    })}
                  </div>
                </div>

                {/* 3. TRẠNG THÁI (Status Selector) - Modern Toggle Buttons */}
                <div className={`space-y-2 transition-all duration-300 ${
                  selectedType !== 'Inventory' ? 'opacity-30 pointer-events-none select-none filter blur-[0.4px]' : 'opacity-100'
                }`}>
                  <div className="mono text-[9.5px] tracking-[0.1em] text-slate-400">TRẠNG THÁI (VOLUME)</div>
                  <div className="grid grid-cols-2 gap-2">
                    <button
                      onClick={toggleAllStatuses}
                      className={`flex items-center gap-2 px-3 py-2 rounded-lg border text-[11px] font-medium transition-all duration-200 ${
                        selectedStatuses.length === INVENTORY_STATUSES.length
                          ? 'bg-yellow-500/10 border-yellow-500/40 text-yellow-400 font-bold'
                          : 'bg-[#101622]/40 border-white/5 text-slate-400 hover:border-slate-700/80 hover:text-slate-300'
                      }`}
                    >
                      <span className={`w-2 h-2 rounded-full ${
                        selectedStatuses.length === INVENTORY_STATUSES.length ? 'bg-yellow-400 animate-pulse' : 'bg-slate-600'
                      }`} />
                      Tất cả
                    </button>
                    {INVENTORY_STATUSES.map(status => {
                      const isChecked = selectedStatuses.includes(status);
                      return (
                        <button
                          key={status}
                          onClick={() => toggleStatus(status)}
                          className={`flex items-center gap-2 px-3 py-2 rounded-lg border text-[10.5px] font-medium transition-all duration-200 ${
                            isChecked
                              ? 'bg-yellow-500/10 border-yellow-500/40 text-yellow-400 font-bold'
                              : 'bg-[#101622]/40 border-white/5 text-slate-400 hover:border-slate-700/80 hover:text-slate-300'
                          }`}
                        >
                          <span className={`w-2 h-2 rounded-full ${
                            isChecked ? 'bg-yellow-400 animate-pulse' : 'bg-slate-600'
                          }`} />
                          {status}
                        </button>
                      );
                    })}
                  </div>
                </div>
              </div>
            </div>
            )}

            {/* B. TOP 10 RACKS (with weight!) */}
            {showTop10 && (
              <div className="bg-[var(--panel)] border border-white/10 border-t-2 border-t-[var(--accent)] rounded-lg backdrop-blur-md shadow-2xl p-4 shrink-0">
              <h3 className="disp text-xs tracking-[0.14em] pb-3 mb-2 border-b border-[var(--line)] text-[var(--accent)]">
                {selectedType === 'Outbound' ? 'TOP 10 BƯU CỤC XUẤT HÀNG' : 'TOP 10 BƯU CỤC TỒN HÀNG'}
              </h3>
              <div className="overflow-x-auto">
                <table className="w-full text-left border-collapse">
                  <thead>
                    <tr className="border-b border-[var(--line)] text-[10px] text-[var(--muted)] uppercase mono font-bold">
                      <th className="py-1 w-6">#</th>
                      <th className="py-1 w-10">Mã</th>
                      <th className="py-1">Bưu Cục</th>
                      <th className="py-1 text-right w-14">{selectedType === 'Outbound' ? 'Xuất' : 'Tồn'}</th>
                      <th className="py-1 text-right w-16">T.lượng</th>
                      <th className="py-1 text-right w-10">{displayUtilizationLabelLc}</th>
                    </tr>
                  </thead>
                  <tbody>
                    {getTop10Chutes().map((chute, index) => {
                      const colors: Record<string, string> = {
                        green: 'var(--green)',
                        yellow: 'var(--yellow)',
                        orange: 'var(--orange)',
                        red: 'var(--red)',
                        darkred: 'var(--red)'
                      };
                      const col = colors[chute.bucket] || '#fff';

                      return (
                        <tr key={chute.areaId} className="border-b border-[#1e2942]/20 last:border-0 hover:bg-white/5 transition-colors cursor-pointer text-[11px]"
                            onMouseEnter={() => {
                              const d = data[chute.areaId];
                              setHoveredRack({ areaId: chute.areaId, name: chute.name, ...d });
                              if (chute.zone) setHoveredZone(chute.zone);
                            }}
                            onMouseLeave={() => {
                              setHoveredRack(null);
                              setHoveredZone(null);
                            }}>
                          <td className="py-1 text-[var(--muted)] mono">{index + 1}</td>
                          <td className="py-1 font-bold text-[var(--cyan)] mono">{chute.areaId}</td>
                          <td className="py-1 truncate max-w-[80px] font-medium text-white/95" title={chute.name}>
                            {chute.name}
                          </td>
                          <td className="py-1 text-right mono font-bold text-white">{chute.current.toLocaleString()}</td>
                          <td className="py-1 text-right mono text-slate-300">{chute.weight.toLocaleString()} kg</td>
                          <td className="py-1 text-right mono font-bold" style={{ color: col }}>{chute.utilization}%</td>
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
            <div className="absolute bottom-16 left-[80px] z-20 flex gap-3 mono text-[10px] text-[var(--muted)] bg-[var(--panel)] border border-[var(--line)] rounded-lg py-2 px-3 backdrop-blur-md shadow-lg transition-all duration-300">
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
            <div className="absolute bottom-16 right-6 z-20 flex gap-3 w-90 justify-between">
              <button onClick={handleResetZoom}
                      className="flex-1 font-sans font-bold text-[10.5px] uppercase py-2.5 px-4 rounded-md border border-white/20 bg-[var(--panel)] text-[var(--muted)] cursor-pointer hover:bg-white/10 hover:text-white transition-all shadow-lg text-center">
                THU NHỎ / RESET
              </button>
              <button onClick={fetchAndUpdateData} onMouseMove={handleGoogleBtnMouseMove} disabled={loading}
                      className="flex-1 google-sync-btn justify-center">
                <span className="w-1.5 h-1.5 rounded-full bg-[#22c55e] animate-pulse shrink-0" />
                {loading ? 'Đang đồng bộ...' : 'Đồng bộ'}
              </button>
            </div>
          )}

          {/* Center Content: Switch between Layout Master and Inbound */}
          <div className={currentView === 'master'
            ? `absolute inset-0 flex items-center justify-center pt-10 pb-20 px-6 transition-all duration-300 ${
                isMobile ? 'pl-6 pr-6' : 'pl-[80px] pr-6'
              }`
            : `absolute inset-0 pt-16 pb-6 overflow-y-auto scrollbar-thin transition-all duration-300 flex flex-col items-center ${
                isMobile 
                  ? 'px-6' 
                  : sidebarHovered 
                    ? 'pl-[264px] pr-[264px]' 
                    : 'pl-[88px] pr-[88px]'
              }`
          }>
            {currentView === 'master' ? (
              renderSVG()
            ) : (() => {
              // 0. Extract available dates
              const inboundDates = Array.from(new Set(inboundData.map(d => d['Ngày vận hành']).filter(Boolean))) as string[];
              inboundDates.sort((a, b) => b.localeCompare(a));
              const activeDate = selectedInboundDate || inboundDates[0] || '';

              // Filter datasets by active date
              const filteredInbound = inboundData.filter(d => d['Ngày vận hành'] === activeDate);
              
              const getLinehaulOperatingDate = (timeStr: string) => {
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
              const filteredLinehaul = linehaulData.filter(d => getLinehaulOperatingDate(d['sendTime']) === activeDate);

              // 1. Aggregate status counts directly from aggregated Inbound sheet (filtered)
              const stages = {
                'Chưa về Hub': { orders: 0, weight: 0 },
                'Đã về Hub': { orders: 0, weight: 0 }
              };
              
              filteredInbound.forEach(d => {
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
              });

              // 2. Hourly timeline distribution from Inbound sheet (based on Inbound Hour/Time of "Đã về Hub" status)
              const hourlyData: Record<string, { hour: string; orders: number; weight: number }> = {};
              for (let i = 0; i < 24; i++) {
                const hStr = `${String(i).padStart(2, '0')}:00`;
                hourlyData[hStr] = { hour: hStr, orders: 0, weight: 0 };
              }
              filteredInbound.forEach(d => {
                if (d['Trạng thái'] === 'Đã về Hub' || d['Trạng thái'] === 'Đã nhập hàng') {
                  const ibTime = d['Inbound Hour'] !== undefined && d['Inbound Hour'] !== null && d['Inbound Hour'] !== '' 
                    ? d['Inbound Hour'] 
                    : d['Inbound Time'];
                  if (ibTime !== undefined && ibTime !== null && ibTime !== '') {
                    const hrVal = parseInt(String(ibTime), 10);
                    if (!isNaN(hrVal) && hrVal >= 0 && hrVal < 24) {
                      const hour = `${String(hrVal).padStart(2, '0')}:00`;
                      if (hourlyData[hour]) {
                        hourlyData[hour].orders += parseInt(d['Volume'], 10) || 0;
                        hourlyData[hour].weight += parseFloat(d['Weight']) || 0;
                      }
                    }
                  }
                }
              });
              const timelineData = Object.values(hourlyData);

              // 2.2. Hourly pickup timeline distribution from Inbound sheet (based on Pickup Time)
              const hourlyPickupData: Record<string, { hour: string; orders: number; weight: number }> = {};
              for (let i = 0; i < 24; i++) {
                const hStr = `${String(i).padStart(2, '0')}:00`;
                hourlyPickupData[hStr] = { hour: hStr, orders: 0, weight: 0 };
              }
              filteredInbound.forEach(d => {
                const pkTime = d['Pickup Time'];
                if (pkTime !== undefined && pkTime !== null && pkTime !== '') {
                  const hrVal = parseInt(String(pkTime), 10);
                  if (!isNaN(hrVal) && hrVal >= 0 && hrVal < 24) {
                    const hour = `${String(hrVal).padStart(2, '0')}:00`;
                    if (hourlyPickupData[hour]) {
                      hourlyPickupData[hour].orders += parseInt(d['Volume'], 10) || 0;
                      hourlyPickupData[hour].weight += parseFloat(d['Weight']) || 0;
                    }
                  }
                }
              });
              const pickupTimelineData = Object.values(hourlyPickupData);

              // 2.3. Hourly pending timeline distribution (based on Pickup Time of "Chưa về Hub" status)
              const hourlyPendingData: Record<string, { hour: string; orders: number; weight: number }> = {};
              for (let i = 0; i < 24; i++) {
                const hStr = `${String(i).padStart(2, '0')}:00`;
                hourlyPendingData[hStr] = { hour: hStr, orders: 0, weight: 0 };
              }
              filteredInbound.forEach(d => {
                if (d['Trạng thái'] !== 'Đã về Hub' && d['Trạng thái'] !== 'Đã nhập hàng') {
                  const pkTime = d['Pickup Time'];
                  if (pkTime !== undefined && pkTime !== null && pkTime !== '') {
                    const hrVal = parseInt(String(pkTime), 10);
                    if (!isNaN(hrVal) && hrVal >= 0 && hrVal < 24) {
                      const hour = `${String(hrVal).padStart(2, '0')}:00`;
                      if (hourlyPendingData[hour]) {
                        hourlyPendingData[hour].orders += parseInt(d['Volume'], 10) || 0;
                        hourlyPendingData[hour].weight += parseFloat(d['Weight']) || 0;
                      }
                    }
                  }
                }
              });
              const pendingTimelineData = Object.values(hourlyPendingData);

              // 3. Group metrics per sending FC (filtered)
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
                const fc = getFC(d['Bưu cục']);
                if (fc) {
                  fc.orders += parseInt(d['Volume'], 10) || 0;
                  fc.weight += parseFloat(d['Weight']) || 0;
                }
              });
              filteredLinehaul.forEach(d => {
                const fcName = d['nextNetworkName'] || 'UNKNOWN';
                const fc = getFC(fcName);
                if (fc && d['Phiếu nhiệm vụ']) {
                  fc.vehicles.add(d['Phiếu nhiệm vụ']);
                }
              });
              const top10FCs = Object.values(fcMetrics)
                .map(item => ({
                  fc: item.fc,
                  vehicles: item.vehicles.size,
                  orders: item.orders,
                  weight: item.weight
                }))
                .sort((a, b) => b.weight - a.weight)
                .slice(0, 10);

              // 4. Incoming vehicles list (filtered to only those not yet unloading/unloaded)
              const incomingVehicles = filteredLinehaul
                .filter(d => !d['unloadingStartTime'] && !d['unloadingEndTime'])
                .map(d => ({
                  taskCode: d['Phiếu nhiệm vụ'] || '',
                  subTaskCode: d['Phiếu nhiệm vụ con'] || '',
                  senderFC: d['nextNetworkName'] || '',
                  sendTime: d['sendTime'] || '',
                  orders: parseInt(d['unloadingBillPiece'], 10) || 0,
                  weight: parseFloat(d['unloadingWeight']) || 0
                }))
                .sort((a, b) => b.sendTime.localeCompare(a.sendTime));

              // 5. Summary stats (filtered)
              const totalFC = new Set(filteredInbound.map(d => d['Bưu cục']).filter(Boolean)).size;
              const totalOrders = filteredInbound.reduce((sum, d) => sum + (parseInt(d['Volume'], 10) || 0), 0);
              const totalWeight = filteredInbound.reduce((sum, d) => sum + (parseFloat(d['Weight']) || 0), 0);
              const totalVehicles = new Set(filteredLinehaul.map(d => d['Phiếu nhiệm vụ']).filter(Boolean)).size;

              return (
                <div className="w-full max-w-7xl mx-auto space-y-6 pb-12 text-slate-100 font-sans">
                  
                  {/* 1. Header & Title Block */}
                  <div className="flex flex-col lg:flex-row lg:items-center justify-between border-b border-white/[0.04] pb-5 gap-4">
                    <div className="space-y-1">
                      <h1 className="text-[22px] font-bold text-white tracking-tight">Inbound Dashboard</h1>
                      <p className="text-xs text-slate-400/65 font-normal">Operational overview of today's inbound activities</p>
                    </div>
                    
                    {/* Grouped Operational Metadata Panel */}
                    <div className="flex flex-wrap items-center gap-4 bg-[#172132]/40 border border-white/[0.04] p-2.5 rounded-2xl text-xs text-slate-300">
                      {/* Operating Date Dropdown */}
                      <div className="flex items-center gap-2">
                        <span className="text-[11px] text-[#94A3B8] font-bold uppercase tracking-wider">Ngày vận hành:</span>
                        <select 
                          value={activeDate} 
                          onChange={e => setSelectedInboundDate(e.target.value)} 
                          className="bg-[#172132] text-white text-xs font-semibold py-1.5 px-3 rounded-xl border border-white/10 outline-none cursor-pointer transition-colors hover:border-white/20"
                        >
                          {inboundDates.length > 0 ? (
                            inboundDates.map(d => (
                              <option key={d} value={d}>{d}</option>
                            ))
                          ) : (
                            <option value="">Chưa có dữ liệu</option>
                          )}
                        </select>
                      </div>

                      <span className="text-xs font-mono text-white/10">|</span>

                      {/* System Status */}
                      <div className="flex items-center gap-1.5 px-3 py-1.5 bg-[#172132] border border-white/10 rounded-xl">
                        <span className="w-1.5 h-1.5 rounded-full bg-[#22C55E] animate-pulse" />
                        <span className="text-slate-300 font-semibold">SYS: ONLINE</span>
                      </div>

                      <span className="text-xs font-mono text-white/10">|</span>
                      
                      {/* Last Synchronization */}
                      <span className="text-xs text-slate-300 font-normal">
                        Last Sync: <span className="font-mono text-white">{new Date().toLocaleTimeString()}</span>
                      </span>

                      <span className="text-xs font-mono text-white/10">|</span>

                      {/* Sync Button */}
                      <button 
                        onClick={fetchAndUpdateData}
                        disabled={loading}
                        className="px-3.5 py-1.5 bg-[#172132] hover:bg-[#1f2c41] text-[#94A3B8] hover:text-white border border-white/10 rounded-xl transition-all duration-[180ms] ease-in-out text-xs font-semibold flex items-center gap-2 cursor-pointer disabled:opacity-50 disabled:cursor-not-allowed"
                      >
                        <RefreshCw size={12} className={loading ? 'animate-spin' : ''} />
                        {loading ? 'Đang đồng bộ...' : 'Đồng bộ'}
                      </button>
                    </div>
                  </div>

                  {/* Row 1: Operational Summary (KPI Cards) */}
                  <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-6">
                    {[
                      { label: 'Inbound volume', val: totalOrders.toLocaleString(), desc: `Arrived rate ${(totalOrders > 0 ? (stages['Đã về Hub'].orders / totalOrders) * 100 : 0).toFixed(1)}%`, icon: Inbox, color: '#22C55E', hoverColor: 'hover:border-[#22C55E]/30' },
                      { label: 'Inbound weight', val: `${totalWeight.toLocaleString()} kg`, desc: `Avg weight ${(totalOrders > 0 ? totalWeight / totalOrders : 0).toFixed(2)} kg/pkg`, icon: TrendingUp, color: '#4F8CFF', hoverColor: 'hover:border-[#4F8CFF]/30' },
                      { label: 'Sending stations', val: totalFC, desc: 'Active sending stations', icon: Sliders, color: '#22D3EE', hoverColor: 'hover:border-[#22D3EE]/30' },
                      { label: 'Vehicles', val: totalVehicles, desc: 'Active Linehaul trucks', icon: Activity, color: '#8B5CF6', hoverColor: 'hover:border-[#8B5CF6]/30' }
                    ].map((card) => {
                      const CardIcon = card.icon;
                      return (
                        <div key={card.label} className={`bg-[#172132] border border-white/[0.04] rounded-2xl p-6 shadow-xl flex flex-col justify-between min-h-[7.5rem] relative overflow-hidden group transition-all duration-[180ms] ease-in-out hover:-translate-y-0.5 hover:shadow-2xl ${card.hoverColor}`}>
                          {/* 1. Icon & Label */}
                          <div className="flex items-center gap-2">
                            <CardIcon size={14} className="text-[#94A3B8]/75" />
                            <span className="text-[12px] text-[#94A3B8]/75 font-semibold tracking-wide sentence-case">{card.label}</span>
                          </div>
                          
                          {/* 2. Centered Value */}
                          <div className="flex-grow flex items-center justify-start my-1">
                            <span className="text-[42px] font-bold text-white tracking-tight leading-none font-mono">{card.val}</span>
                          </div>
                          
                          {/* 3. Supporting Metric */}
                          <div className="text-[12px] text-[#94A3B8]/65 font-normal flex items-center gap-1.5">
                            <span className="inline-block w-1.5 h-1.5 rounded-full animate-pulse" style={{ backgroundColor: card.color }} />
                            {card.desc}
                          </div>
                        </div>
                      );
                    })}
                  </div>

                  {/* Row 2: Primary Operational Analytics */}
                  <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
                    {/* Pickup Volume Chart */}
                    <div className="bg-[#172132] border border-white/[0.04] rounded-2xl p-6 shadow-xl relative overflow-hidden group hover:border-[#4F8CFF]/20 transition-all duration-[180ms] ease-in-out flex flex-col justify-between min-h-[22rem]">
                      {/* Card Header & Description */}
                      <div className="flex items-start gap-3 pb-3.5 border-b border-white/[0.04]">
                        <div className="w-8 h-8 rounded-lg bg-[#4F8CFF]/10 text-[#4F8CFF] flex items-center justify-center shrink-0">
                          <Sliders size={16} strokeWidth={2} />
                        </div>
                        <div>
                          <h3 className="text-[15px] font-semibold text-white leading-tight">Pickup volume</h3>
                          <p className="text-xs text-slate-400/65 mt-0.5">Theo dõi sản lượng Pickup của bưu cục</p>
                        </div>
                        <div className="ml-auto text-right">
                          <span className="text-[24px] font-bold text-white tracking-tight leading-none block font-mono">{totalOrders.toLocaleString()}</span>
                          <span className="text-[10px] text-slate-400/75 uppercase mt-1 block">Tổng đơn gom</span>
                        </div>
                      </div>

                      {/* Content Area: Chart viewport (70~80% height) */}
                      <div className="flex-grow flex items-center justify-center mt-3">
                        {(() => {
                          const vals = pickupTimelineData.map(x => x.orders);
                          const maxValReal = Math.max(...vals, 0);
                          const minValReal = Math.min(...vals, 0);
                          const valRange = maxValReal - minValReal;
                          const yPad = valRange === 0 ? (maxValReal === 0 ? 10 : maxValReal * 0.15) : valRange * 0.15;
                          const maxVal = maxValReal + yPad;
                          const minVal = Math.max(0, minValReal - yPad);
                          const effectiveRange = maxVal - minVal || 1;
                          const allZeroOrEqual = vals.every(v => v === vals[0]);

                          const width = 500;
                          const height = 180;
                          const paddingLeft = 30;
                          const paddingRight = 10;
                          const paddingTop = 10;
                          const paddingBottom = 20;

                          const chartW = width - paddingLeft - paddingRight;
                          const chartH = height - paddingTop - paddingBottom;
                          const dx = chartW / 23;

                          const pts = pickupTimelineData.map((d, i) => ({
                            x: paddingLeft + i * dx,
                            y: height - paddingBottom - ((d.orders - minVal) / effectiveRange) * chartH
                          }));

                          let splinePath = '';
                          if (pts.length > 0) {
                            splinePath = `M ${pts[0].x} ${pts[0].y}`;
                            for (let i = 0; i < pts.length - 1; i++) {
                              const p0 = pts[i];
                              const p1 = pts[i + 1];
                              const cpX1 = p0.x + (p1.x - p0.x) / 3;
                              const cpY1 = p0.y;
                              const cpX2 = p0.x + 2 * (p1.x - p0.x) / 3;
                              const cpY2 = p1.y;
                              splinePath += ` C ${cpX1} ${cpY1}, ${cpX2} ${cpY2}, ${p1.x} ${p1.y}`;
                            }
                          }

                          const areaPath = splinePath 
                            ? `${splinePath} L ${pts[pts.length - 1].x} ${height - paddingBottom} L ${pts[0].x} ${height - paddingBottom} Z` 
                            : '';

                          return (
                            <div className="w-full">
                              <svg viewBox={`0 0 ${width} ${height}`} className="w-full h-full">
                                <defs>
                                  <linearGradient id="pk-blue-2" x1="0" y1="0" x2="0" y2="1">
                                    <stop offset="0%" stopColor="#4F8CFF" stopOpacity="0.15" />
                                    <stop offset="100%" stopColor="#4F8CFF" stopOpacity="0" />
                                  </linearGradient>
                                </defs>

                                {/* Grid lines - exactly 5 lines */}
                                {[0, 0.25, 0.5, 0.75, 1].map((ratio, idx) => {
                                  const y = paddingTop + ratio * chartH;
                                  return (
                                    <line key={idx} x1={paddingLeft} y1={y} x2={width - paddingRight} y2={y} stroke="rgba(255,255,255,0.025)" strokeWidth="1" />
                                  );
                                })}

                                {allZeroOrEqual ? (
                                  <>
                                    <line x1={paddingLeft} y1={paddingTop + 0.5 * chartH} x2={width - paddingRight} y2={paddingTop + 0.5 * chartH} stroke="rgba(255,255,255,0.06)" strokeWidth="1.5" strokeDasharray="4 4" />
                                    <text x={width / 2} y={paddingTop + 0.5 * chartH - 6} fill="#94A3B8" fontSize="8" textAnchor="middle" className="font-sans font-medium">Không ghi nhận sản lượng phát sinh</text>
                                  </>
                                ) : (
                                  <>
                                    {/* Glow area & Line */}
                                    {areaPath && <path d={areaPath} fill="url(#pk-blue-2)" />}
                                    {splinePath && <path d={splinePath} fill="none" stroke="#4F8CFF" strokeWidth="2.5" strokeLinecap="round" />}

                                    {/* Interactive hovering points */}
                                    {pts.map((p, i) => (
                                      <circle key={i} cx={p.x} cy={p.y} r="3" fill="#4F8CFF" className="transition-all duration-150 hover:r-4 cursor-pointer" />
                                    ))}
                                  </>
                                )}

                                {/* X labels */}
                                <text x={paddingLeft} y={height - 4} fill="#94A3B8" fontSize="8" className="font-mono text-left">00:00</text>
                                <text x={width - paddingRight} y={height - 4} fill="#94A3B8" fontSize="8" textAnchor="end" className="font-mono">23:00</text>
                              </svg>
                            </div>
                          );
                        })()}
                      </div>
                      
                      {/* Optional Footer */}
                      <div className="pt-2 border-t border-white/[0.04] text-[11px] text-[#94A3B8] flex justify-between">
                        <span>Last updated: just now</span>
                        <span>Interval: 24h</span>
                      </div>
                    </div>

                    {/* Arrival Volume Chart */}
                    <div className="bg-[#172132] border border-white/[0.04] rounded-2xl p-6 shadow-xl relative overflow-hidden group hover:border-[#22C55E]/30 transition-all duration-[180ms] ease-in-out flex flex-col justify-between min-h-[22rem]">
                      {/* Card Header & Description */}
                      <div className="flex items-start gap-3 pb-3.5 border-b border-white/[0.04]">
                        <div className="w-8 h-8 rounded-lg bg-[#22C55E]/10 text-[#22C55E] flex items-center justify-center shrink-0">
                          <TrendingUp size={16} strokeWidth={2} />
                        </div>
                        <div>
                          <h3 className="text-[15px] font-semibold text-white leading-tight">Arrival volume</h3>
                          <p className="text-xs text-slate-400/65 mt-0.5">Theo dõi sản lượng hàng đã nhập HUB</p>
                        </div>
                        <div className="ml-auto text-right">
                          <span className="text-[24px] font-bold text-white tracking-tight leading-none block font-mono">{stages['Đã về Hub'].orders.toLocaleString()}</span>
                          <span className="text-[10px] text-slate-400/75 uppercase mt-1 block">Đơn dỡ thành công</span>
                        </div>
                      </div>

                      {/* Content Area: Chart viewport (70~80% height) */}
                      <div className="flex-grow flex items-center justify-center mt-3">
                        {(() => {
                          const vals = timelineData.map(x => x.orders);
                          const maxValReal = Math.max(...vals, 0);
                          const minValReal = Math.min(...vals, 0);
                          const valRange = maxValReal - minValReal;
                          const yPad = valRange === 0 ? (maxValReal === 0 ? 10 : maxValReal * 0.15) : valRange * 0.15;
                          const maxVal = maxValReal + yPad;
                          const minVal = Math.max(0, minValReal - yPad);
                          const effectiveRange = maxVal - minVal || 1;
                          const allZeroOrEqual = vals.every(v => v === vals[0]);

                          const width = 500;
                          const height = 180;
                          const paddingLeft = 30;
                          const paddingRight = 10;
                          const paddingTop = 10;
                          const paddingBottom = 20;

                          const chartW = width - paddingLeft - paddingRight;
                          const chartH = height - paddingTop - paddingBottom;
                          const dx = chartW / 23;

                          const pts = timelineData.map((d, i) => ({
                            x: paddingLeft + i * dx,
                            y: height - paddingBottom - ((d.orders - minVal) / effectiveRange) * chartH
                          }));

                          let splinePath = '';
                          if (pts.length > 0) {
                            splinePath = `M ${pts[0].x} ${pts[0].y}`;
                            for (let i = 0; i < pts.length - 1; i++) {
                              const p0 = pts[i];
                              const p1 = pts[i + 1];
                              const cpX1 = p0.x + (p1.x - p0.x) / 3;
                              const cpY1 = p0.y;
                              const cpX2 = p0.x + 2 * (p1.x - p0.x) / 3;
                              const cpY2 = p1.y;
                              splinePath += ` C ${cpX1} ${cpY1}, ${cpX2} ${cpY2}, ${p1.x} ${p1.y}`;
                            }
                          }

                          const areaPath = splinePath 
                            ? `${splinePath} L ${pts[pts.length - 1].x} ${height - paddingBottom} L ${pts[0].x} ${height - paddingBottom} Z` 
                            : '';

                          return (
                            <div className="w-full">
                              <svg viewBox={`0 0 ${width} ${height}`} className="w-full h-full">
                                <defs>
                                  <linearGradient id="arr-green-2" x1="0" y1="0" x2="0" y2="1">
                                    <stop offset="0%" stopColor="#22C55E" stopOpacity="0.15" />
                                    <stop offset="100%" stopColor="#22C55E" stopOpacity="0" />
                                  </linearGradient>
                                </defs>

                                {/* Grid lines - exactly 5 lines */}
                                {[0, 0.25, 0.5, 0.75, 1].map((ratio, idx) => {
                                  const y = paddingTop + ratio * chartH;
                                  return (
                                    <line key={idx} x1={paddingLeft} y1={y} x2={width - paddingRight} y2={y} stroke="rgba(255,255,255,0.025)" strokeWidth="1" />
                                  );
                                })}

                                {allZeroOrEqual ? (
                                  <>
                                    <line x1={paddingLeft} y1={paddingTop + 0.5 * chartH} x2={width - paddingRight} y2={paddingTop + 0.5 * chartH} stroke="rgba(255,255,255,0.06)" strokeWidth="1.5" strokeDasharray="4 4" />
                                    <text x={width / 2} y={paddingTop + 0.5 * chartH - 6} fill="#94A3B8" fontSize="8" textAnchor="middle" className="font-sans font-medium">Không ghi nhận sản lượng phát sinh</text>
                                  </>
                                ) : (
                                  <>
                                    {/* Glow area & Line */}
                                    {areaPath && <path d={areaPath} fill="url(#arr-green-2)" />}
                                    {splinePath && <path d={splinePath} fill="none" stroke="#22C55E" strokeWidth="2.5" strokeLinecap="round" />}

                                    {/* Interactive hovering points */}
                                    {pts.map((p, i) => (
                                      <circle key={i} cx={p.x} cy={p.y} r="3" fill="#22C55E" className="transition-all duration-150 hover:r-4 cursor-pointer" />
                                    ))}
                                  </>
                                )}

                                {/* X labels */}
                                <text x={paddingLeft} y={height - 4} fill="#94A3B8" fontSize="8" className="font-mono text-left">00:00</text>
                                <text x={width - paddingRight} y={height - 4} fill="#94A3B8" fontSize="8" textAnchor="end" className="font-mono">23:00</text>
                              </svg>
                            </div>
                          );
                        })()}
                      </div>

                      {/* Optional Footer & Legend */}
                      <div className="pt-2 border-t border-white/[0.04] text-[11px] text-slate-400/65 flex justify-between items-center">
                        <div className="flex items-center gap-3">
                          <span className="flex items-center gap-1.5">
                            <span className="w-1.5 h-1.5 rounded-full bg-[#22C55E]" />
                            Sản lượng Arrival
                          </span>
                          <span>•</span>
                          <span>Khung giờ: 24h</span>
                        </div>
                        <span>Last updated: just now</span>
                      </div>
                    </div>
                  </div>

                  {/* Row 3: Operational Monitoring */}
                  <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
                    {/* Top 10 Sending Stations */}
                    <div className="bg-[#172132] border border-white/[0.04] rounded-2xl p-6 shadow-xl flex flex-col justify-between h-[25rem] group hover:border-[#06B6D4]/30 transition-all duration-[180ms] ease-in-out hover:-translate-y-0.5 hover:shadow-2xl">
                      {/* Widget Header: Icon + Title + Description + Divider */}
                      <div className="flex items-start gap-3 pb-3.5 border-b border-white/[0.04] mb-3.5">
                        <div className="w-8 h-8 rounded-lg bg-[#06B6D4]/10 text-[#06B6D4] flex items-center justify-center shrink-0">
                          <ListOrdered size={16} strokeWidth={2} />
                        </div>
                        <div>
                          <h3 className="text-[15px] font-semibold text-white leading-tight">Top 10 sending stations</h3>
                          <p className="text-xs text-slate-400/65 mt-0.5">Top bưu cục gửi hàng nhiều nhất về HUB</p>
                        </div>
                      </div>
                      
                      {/* Leaderboard content */}
                      <div className="overflow-y-auto flex-1 pr-1 scrollbar-thin my-2">
                        {(() => {
                          const maxOrders = Math.max(...top10FCs.map(x => x.orders), 1);
                          return (
                            <table className="w-full text-left border-collapse text-xs">
                              <thead>
                                <tr className="text-slate-400/75 border-b border-white/[0.04] uppercase tracking-wider text-[9px] font-bold">
                                  <th className="py-3 w-8">#</th>
                                  <th className="py-3">FC</th>
                                  <th className="py-3 text-right">Số xe</th>
                                  <th className="py-3 text-right">Đơn</th>
                                  <th className="py-3 text-right">Tải trọng</th>
                                </tr>
                              </thead>
                              <tbody>
                                {top10FCs.slice(0, 8).map((row, idx) => {
                                  const rank = idx + 1;
                                  const rankColorClass = rank === 1 
                                    ? "text-[#06B6D4]" 
                                    : rank === 2 
                                      ? "text-[#38BDF8]" 
                                      : rank === 3 
                                        ? "text-slate-200" 
                                        : "text-slate-400/65";
                                  return (
                                    <tr key={row.fc} className="border-b border-white/[0.03] last:border-0 hover:bg-white/[0.02] even:bg-white/[0.005] transition-colors duration-150">
                                      <td className={`py-3.5 font-bold font-mono ${rankColorClass}`}>{rank}</td>
                                      <td className="py-3.5">
                                        <div className="flex flex-col gap-1.5">
                                          <span className="font-semibold text-white">{row.fc}</span>
                                          <div className="w-20 h-1 bg-white/[0.04] rounded-full overflow-hidden">
                                            <div className="h-full bg-[#06B6D4] rounded-full" style={{ width: `${(row.orders / maxOrders) * 100}%` }} />
                                          </div>
                                        </div>
                                      </td>
                                      <td className="py-3.5 text-right font-mono text-slate-300">{row.vehicles}</td>
                                      <td className="py-3.5 text-right font-mono text-slate-300">{row.orders.toLocaleString()}</td>
                                      <td className="py-3.5 text-right font-mono font-semibold text-[#06B6D4]">{row.weight.toLocaleString()} kg</td>
                                    </tr>
                                  );
                                })}
                              </tbody>
                            </table>
                          );
                        })()}
                      </div>

                      {/* Footer */}
                      <div className="pt-2 border-t border-white/[0.04] text-[11px] text-slate-400/65 flex justify-between">
                        <span>Ranked by order count</span>
                        <span>Top 8 stations</span>
                      </div>
                    </div>

                    {/* Vehicles in Transit */}
                    <div className="bg-[#172132] border border-white/[0.04] rounded-2xl p-6 shadow-xl flex flex-col justify-between h-[25rem] group hover:border-[#8B5CF6]/30 transition-all duration-[180ms] ease-in-out hover:-translate-y-0.5 hover:shadow-2xl">
                      {/* Widget Header: Icon + Title + Description + Divider */}
                      <div className="flex items-start gap-3 pb-3.5 border-b border-white/[0.04] mb-3.5">
                        <div className="w-8 h-8 rounded-lg bg-[#8B5CF6]/10 text-[#8B5CF6] flex items-center justify-center shrink-0">
                          <Truck size={16} strokeWidth={2} />
                        </div>
                        <div>
                          <h3 className="text-[15px] font-semibold text-white leading-tight">Vehicles in transit</h3>
                          <p className="text-xs text-slate-400/65 mt-0.5">Danh sách xe đang trên đường về HUB</p>
                        </div>
                      </div>

                      {/* Content Area */}
                      <div className="overflow-y-auto flex-1 pr-1 scrollbar-thin my-2 space-y-2">
                        {incomingVehicles.length === 0 ? (
                          <div className="h-full flex flex-col items-center justify-center text-center py-4 space-y-3">
                            <div className="w-12 h-12 rounded-full bg-white/[0.02] border border-white/[0.04] flex items-center justify-center text-[#8B5CF6] opacity-75">
                              <Truck size={24} strokeWidth={1.5} />
                            </div>
                            <div className="space-y-1">
                              <p className="text-sm font-semibold text-white">No active vehicles</p>
                              <p className="text-xs text-slate-400/65 max-w-[200px] mx-auto">No vehicles are currently travelling to HUB.</p>
                              <p className="text-[10px] text-slate-500 font-mono mt-1">Checked at {new Date().toLocaleTimeString()}</p>
                            </div>
                            <button onClick={fetchAndUpdateData} disabled={loading} className="px-3.5 py-1.5 bg-[#172132] hover:bg-[#1f2c41] text-[#94A3B8] hover:text-white border border-white/10 rounded-xl transition-all duration-[180ms] ease-in-out text-[11px] font-semibold flex items-center gap-1.5 cursor-pointer disabled:opacity-50">
                              <RefreshCw size={10} className={loading ? 'animate-spin' : ''} />
                              Refresh status
                            </button>
                          </div>
                        ) : (
                          incomingVehicles.map((row, idx) => {
                            const timeMatch = row.sendTime.match(/\s+(\d{2}:\d{2})/);
                            const sendHour = timeMatch ? timeMatch[1] : row.sendTime;
                            return (
                              <div key={`${row.taskCode}-${idx}`} className="flex items-center justify-between p-2.5 bg-white/[0.01] border border-white/[0.04] rounded-xl hover:border-[#8B5CF6]/30 hover:bg-white/[0.02] transition-all duration-[180ms] ease-in-out">
                                <div className="space-y-1">
                                  <div className="flex items-center gap-1.5">
                                    <span className="text-xs font-bold font-mono text-[#8B5CF6]">{row.taskCode}</span>
                                    <span className="text-[9px] px-2 py-0.5 rounded-lg bg-[#8B5CF6]/10 text-[#8B5CF6] font-semibold">Gửi {sendHour}</span>
                                  </div>
                                  <div className="text-xs text-slate-400/65">{row.senderFC}</div>
                                </div>
                                <div className="text-right space-y-0.5">
                                  <div className="text-xs font-semibold text-white font-mono">{row.weight.toLocaleString()} kg</div>
                                  <div className="text-[10px] text-slate-400/65 font-mono">{row.orders.toLocaleString()} đơn</div>
                                </div>
                              </div>
                            );
                          })
                        )}
                      </div>

                      {/* Footer */}
                      <div className="pt-2 border-t border-white/[0.04] text-[11px] text-slate-400/65 flex justify-between">
                        <span>Total: {incomingVehicles.length} trucks</span>
                        <span>Last sync: just now</span>
                      </div>
                    </div>
                  </div>

                  {/* Row 4: Operational Summary */}
                  <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
                    {/* Selection Status */}
                    <div className="bg-[#172132] border border-white/[0.04] rounded-2xl p-6 shadow-xl flex flex-col justify-between h-[22rem] group hover:border-[#8B5CF6]/30 transition-all duration-[180ms] ease-in-out hover:-translate-y-0.5 hover:shadow-2xl">
                      {/* Widget Header: Icon + Title + Description + Divider */}
                      <div className="flex items-start gap-3 pb-3.5 border-b border-white/[0.04] mb-3.5">
                        <div className="w-8 h-8 rounded-lg bg-[#8B5CF6]/10 text-[#8B5CF6] flex items-center justify-center shrink-0">
                          <Activity size={16} strokeWidth={2} />
                        </div>
                        <div>
                          <h3 className="text-[15px] font-semibold text-white leading-tight">Selection status</h3>
                          <p className="text-xs text-slate-400/65 mt-0.5">Tỷ lệ phân bổ trạng thái hàng nhập HUB</p>
                        </div>
                      </div>

                      {/* Donut Chart Content */}
                      <div className="py-2 flex justify-center items-center flex-grow">
                        {(() => {
                          const arrived = stages['Đã về Hub'].orders;
                          const inTransit = stages['Chưa về Hub'].orders;
                          const total = arrived + inTransit;
                          
                          const radius = 38;
                          const circumference = 2 * Math.PI * radius;
                          const arrivedPercent = total > 0 ? (arrived / total) * 100 : 0;
                          const inTransitPercent = total > 0 ? (inTransit / total) * 100 : 0;

                          const strokeArrived = (arrivedPercent / 100) * circumference;
                          const strokeInTransit = (inTransitPercent / 100) * circumference;
                          
                          return (
                            <div className="relative flex items-center justify-center scale-95">
                              <svg width="150" height="150" viewBox="0 0 100 100">
                                <circle cx="50" cy="50" r={radius} fill="none" stroke="rgba(255,255,255,0.03)" strokeWidth="10" />
                                <circle 
                                  cx="50" 
                                  cy="50" 
                                  r={radius} 
                                  fill="none" 
                                  stroke="#22C55E" 
                                  strokeWidth="10" 
                                  strokeDasharray={`${strokeArrived} ${circumference - strokeArrived}`}
                                  strokeDashoffset={circumference}
                                  transform="rotate(-90 50 50)"
                                  strokeLinecap="round"
                                />
                                <circle 
                                  cx="50" 
                                  cy="50" 
                                  r={radius} 
                                  fill="none" 
                                  stroke="#8B5CF6" 
                                  strokeWidth="10" 
                                  strokeDasharray={`${strokeInTransit} ${circumference - strokeInTransit}`}
                                  strokeDashoffset={circumference - strokeArrived}
                                  transform="rotate(-90 50 50)"
                                  strokeLinecap="round"
                                />
                              </svg>
                              <div className="absolute flex flex-col items-center justify-center text-center">
                                <span className="text-[28px] font-bold text-white tracking-tight leading-none font-mono">{total.toLocaleString()}</span>
                                <span className="text-[9px] text-slate-400/75 font-semibold uppercase mt-1 tracking-wider">Total Orders</span>
                              </div>
                            </div>
                          );
                        })()}
                      </div>

                      {/* Legend / Status values */}
                      <div className="grid grid-cols-2 gap-3 text-xs pt-3 border-t border-white/[0.04]">
                        <div className="text-center">
                          <span className="text-[11px] text-slate-400/75 uppercase font-bold flex items-center justify-center gap-1.5">
                            <i className="w-1.5 h-1.5 rounded-full bg-[#22C55E]" />
                            Đã về Hub
                          </span>
                          <span className="text-[13px] font-bold text-white font-mono mt-0.5 block">
                            {stages['Đã về Hub'].orders.toLocaleString()}
                          </span>
                        </div>
                        <div className="text-center">
                          <span className="text-[11px] text-slate-400/75 uppercase font-bold flex items-center justify-center gap-1.5">
                            <i className="w-1.5 h-1.5 rounded-full bg-[#8B5CF6]" />
                            Chưa về HUB
                          </span>
                          <span className="text-[13px] font-bold text-white font-mono mt-0.5 block">
                            {stages['Chưa về Hub'].orders.toLocaleString()}
                          </span>
                        </div>
                      </div>
                    </div>

                    {/* Inbound Pending Trend */}
                    <div className="bg-[#172132] border border-white/[0.04] rounded-2xl p-6 shadow-xl relative overflow-hidden group hover:border-[#8B5CF6]/30 transition-all duration-[180ms] ease-in-out flex flex-col justify-between h-[22rem] hover:-translate-y-0.5 hover:shadow-2xl">
                      {/* Widget Header: Icon + Title + Description + Divider */}
                      <div className="flex items-start gap-3 pb-3.5 border-b border-white/[0.04] mb-3.5">
                        <div className="w-8 h-8 rounded-lg bg-[#8B5CF6]/10 text-[#8B5CF6] flex items-center justify-center shrink-0">
                          <Activity size={16} strokeWidth={2} />
                        </div>
                        <div>
                          <h3 className="text-[15px] font-semibold text-white leading-tight">Inbound pending trend</h3>
                          <p className="text-xs text-slate-400/65 mt-0.5">Theo dõi lượng hàng còn chờ nhập HUB</p>
                        </div>
                        <div className="ml-auto text-right">
                          <span className="text-[24px] font-bold text-white tracking-tight leading-none block font-mono">{stages['Chưa về Hub'].orders.toLocaleString()}</span>
                          <span className="text-[10px] text-slate-400/75 uppercase mt-1 block">Đơn chờ dỡ</span>
                        </div>
                      </div>

                      {/* Content Area: Chart viewport (70~80% height) */}
                      <div className="flex-grow flex items-center justify-center mt-3">
                        {(() => {
                          const vals = pendingTimelineData.map(x => x.orders);
                          const maxValReal = Math.max(...vals, 0);
                          const minValReal = Math.min(...vals, 0);
                          const valRange = maxValReal - minValReal;
                          const yPad = valRange === 0 ? (maxValReal === 0 ? 10 : maxValReal * 0.15) : valRange * 0.15;
                          const maxVal = maxValReal + yPad;
                          const minVal = Math.max(0, minValReal - yPad);
                          const effectiveRange = maxVal - minVal || 1;
                          const allZeroOrEqual = vals.every(v => v === vals[0]);

                          const width = 500;
                          const height = 180;
                          const paddingLeft = 30;
                          const paddingRight = 10;
                          const paddingTop = 10;
                          const paddingBottom = 20;

                          const chartW = width - paddingLeft - paddingRight;
                          const chartH = height - paddingTop - paddingBottom;
                          const dx = chartW / 23;

                          const pts = pendingTimelineData.map((d, i) => ({
                            x: paddingLeft + i * dx,
                            y: height - paddingBottom - ((d.orders - minVal) / effectiveRange) * chartH
                          }));

                          let splinePath = '';
                          if (pts.length > 0) {
                            splinePath = `M ${pts[0].x} ${pts[0].y}`;
                            for (let i = 0; i < pts.length - 1; i++) {
                              const p0 = pts[i];
                              const p1 = pts[i + 1];
                              const cpX1 = p0.x + (p1.x - p0.x) / 3;
                              const cpY1 = p0.y;
                              const cpX2 = p0.x + 2 * (p1.x - p0.x) / 3;
                              const cpY2 = p1.y;
                              splinePath += ` C ${cpX1} ${cpY1}, ${cpX2} ${cpY2}, ${p1.x} ${p1.y}`;
                            }
                          }

                          const areaPath = splinePath 
                            ? `${splinePath} L ${pts[pts.length - 1].x} ${height - paddingBottom} L ${pts[0].x} ${height - paddingBottom} Z` 
                            : '';

                          return (
                            <div className="w-full">
                              <svg viewBox={`0 0 ${width} ${height}`} className="w-full h-full">
                                <defs>
                                  <linearGradient id="err-purple-2" x1="0" y1="0" x2="0" y2="1">
                                    <stop offset="0%" stopColor="#8B5CF6" stopOpacity="0.15" />
                                    <stop offset="100%" stopColor="#8B5CF6" stopOpacity="0" />
                                  </linearGradient>
                                </defs>

                                {/* Grid lines - exactly 5 lines */}
                                {[0, 0.25, 0.5, 0.75, 1].map((ratio, idx) => {
                                  const y = paddingTop + ratio * chartH;
                                  return (
                                    <line key={idx} x1={paddingLeft} y1={y} x2={width - paddingRight} y2={y} stroke="rgba(255,255,255,0.025)" strokeWidth="1" />
                                  );
                                })}

                                {allZeroOrEqual ? (
                                  <>
                                    <line x1={paddingLeft} y1={paddingTop + 0.5 * chartH} x2={width - paddingRight} y2={paddingTop + 0.5 * chartH} stroke="rgba(255,255,255,0.06)" strokeWidth="1.5" strokeDasharray="4 4" />
                                    <text x={width / 2} y={paddingTop + 0.5 * chartH - 6} fill="#94A3B8" fontSize="8" textAnchor="middle" className="font-sans font-medium">Không ghi nhận sản lượng phát sinh</text>
                                  </>
                                ) : (
                                  <>
                                    {/* Glow area & Line */}
                                    {areaPath && <path d={areaPath} fill="url(#err-purple-2)" />}
                                    {splinePath && <path d={splinePath} fill="none" stroke="#8B5CF6" strokeWidth="2.5" strokeLinecap="round" />}

                                    {/* Hover dots */}
                                    {pts.map((p, i) => (
                                      <circle key={i} cx={p.x} cy={p.y} r="3" fill="#8B5CF6" className="transition-all duration-150 hover:r-4 cursor-pointer" />
                                    ))}
                                  </>
                                )}

                                {/* X labels */}
                                <text x={paddingLeft} y={height - 4} fill="#94A3B8" fontSize="8" className="font-mono text-left">00:00</text>
                                <text x={width - paddingRight} y={height - 4} fill="#94A3B8" fontSize="8" textAnchor="end" className="font-mono">23:00</text>
                              </svg>
                            </div>
                          );
                        })()}
                      </div>

                      {/* Optional Footer & Legend */}
                      <div className="pt-2 border-t border-white/[0.04] text-[11px] text-slate-400/65 flex justify-between items-center">
                        <div className="flex items-center gap-3">
                          <span className="flex items-center gap-1.5">
                            <span className="w-1.5 h-1.5 rounded-full bg-[#8B5CF6]" />
                            Sản lượng chờ dỡ
                          </span>
                          <span>•</span>
                          <span>Khung giờ: 24h</span>
                        </div>
                        <span>Last updated: just now</span>
                      </div>
                    </div>
                  </div>
                </div>
              );
            })()}
          </div>
        </>
      ) : ( 
        /* ── MOBILE LAYOUT ── */
        <>
          <div className="w-full h-full pt-16 pb-24 px-4 overflow-hidden flex flex-col justify-between">
            {activeTab === 'layout' && (
              <div className="w-full h-full flex flex-col justify-between relative pt-12">
                {/* Mobile Filter Bar & Sync Button consolidated */}
                <div className="absolute top-2 left-2 right-2 z-30 flex flex-col gap-1.5 bg-[#121824]/95 backdrop-blur border border-white/10 rounded-md p-1.5 shadow-xl">
                  <div className="flex gap-1.5 items-center">
                    {/* Type Select */}
                    <select value={selectedType} onChange={e => setSelectedType(e.target.value as any)} 
                            className="flex-1 bg-[#0a0e14] text-white text-[10px] font-bold py-1.5 px-2 rounded border border-white/5 outline-none cursor-pointer">
                      <option value="Outbound">Outbound</option>
                      <option value="Backlog">Backlog</option>
                      <option value="Inventory">Volume</option>
                    </select>

                    {/* Date Select */}
                    <select value={selectedDate} onChange={e => setSelectedDate(e.target.value)} 
                            className="flex-1 bg-[#0a0e14] text-white text-[10px] font-bold py-1.5 px-2 rounded border border-white/5 outline-none cursor-pointer">
                      {availableDates.length > 0 ? (
                        availableDates.map(d => (
                          <option key={d} value={d}>{d}</option>
                        ))
                      ) : (
                        <option value="">Chưa có dữ liệu</option>
                      )}
                    </select>

                    {/* Inline Sync Button */}
                    <button onClick={fetchAndUpdateData} onMouseMove={handleGoogleBtnMouseMove} disabled={loading} 
                            className="google-sync-btn px-2.5 py-1 text-[10px] gap-1 shadow-lg shrink-0">
                      <span className="w-1.5 h-1.5 rounded-full bg-[#22c55e] animate-pulse shrink-0" />
                      {loading ? '...' : 'Đồng bộ'}
                    </button>
                  </div>

                  {/* Mobile Inventory Status Filter */}
                  {selectedType === 'Inventory' && (
                    <div className="flex items-center gap-1.5 overflow-x-auto py-1 scrollbar-none border-t border-white/5 mt-1"
                         style={{ scrollbarWidth: 'none', msOverflowStyle: 'none' }}>
                      <button
                        onClick={toggleAllStatuses}
                        className={`px-2 py-0.5 rounded-full border text-[9px] font-medium transition-all duration-200 shrink-0 ${
                          selectedStatuses.length === INVENTORY_STATUSES.length
                            ? 'bg-yellow-500/10 border-yellow-500/40 text-yellow-400 font-bold'
                            : 'bg-[#121824]/40 border-white/5 text-slate-400'
                        }`}
                      >
                        Tất cả
                      </button>
                      {INVENTORY_STATUSES.map(status => {
                        const isChecked = selectedStatuses.includes(status);
                        return (
                          <button
                            key={status}
                            onClick={() => toggleStatus(status)}
                            className={`px-2 py-0.5 rounded-full border text-[9px] font-medium transition-all duration-200 shrink-0 ${
                              isChecked
                                ? 'bg-yellow-500/10 border-yellow-500/40 text-yellow-400 font-bold'
                                : 'bg-[#121824]/40 border-white/5 text-slate-400'
                            }`}
                          >
                            {status}
                          </button>
                        );
                      })}
                    </div>
                  )}
                </div>

                {/* Floating Zoom controls */}
                <div className="mobile-fab-container">
                  <button className="mobile-fab text-base font-bold" onClick={handleZoomIn}>＋</button>
                  <button className="mobile-fab text-base font-bold" onClick={handleZoomOut}>－</button>
                  <button className="mobile-fab text-sm" onClick={handleResetZoom}>🔄</button>
                </div>

                {renderSVG()}

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
                <div className="bg-[var(--panel)] border border-white/10 border-t-2 border-t-[var(--accent)] rounded-lg p-4 shadow-xl">
                  <h3 className="disp text-xs tracking-[0.14em] pb-3 mb-3 border-b border-[var(--line)] text-[var(--accent)] text-center">
                    {selectedType === 'Outbound' ? 'TOP 10 BƯU CỤC XUẤT HÀNG' : 'TOP 10 BƯU CỤC TỒN HÀNG'}
                  </h3>
                  <table className="w-full text-left border-collapse">
                    <thead>
                      <tr className="border-b border-[var(--line)] text-[10px] text-[var(--muted)] uppercase mono font-bold">
                        <th className="py-2 w-8">#</th>
                        <th className="py-2 w-12">Mã</th>
                        <th className="py-2">Bưu Cục</th>
                        <th className="py-2 text-right w-16">{selectedType === 'Outbound' ? 'Lượng xuất' : 'Tồn'}</th>
                        <th className="py-2 text-right w-16">T.lượng</th>
                        <th className="py-2 text-right w-12">%</th>
                      </tr>
                    </thead>
                    <tbody>
                      {getTop10Chutes().map((chute, index) => {
                        const colors: Record<string, string> = {
                          green: 'var(--green)',
                          yellow: 'var(--yellow)',
                          orange: 'var(--orange)',
                          red: 'var(--red)',
                          darkred: 'var(--red)'
                        };
                        const col = colors[chute.bucket] || '#fff';
                        return (
                          <tr key={chute.areaId} className="border-b border-[#1e2942]/20 last:border-0 hover:bg-white/5 transition-colors text-[11px]">
                            <td className="py-2 text-[var(--muted)] mono">{index + 1}</td>
                            <td className="py-2 font-bold text-[var(--cyan)] mono">{chute.areaId}</td>
                            <td className="py-2 truncate max-w-[90px] font-medium text-white/95">{chute.name}</td>
                            <td className="py-2 text-right mono font-bold text-white">{chute.current.toLocaleString()}</td>
                            <td className="py-2 text-right mono text-slate-300">{chute.weight.toLocaleString()} kg</td>
                            <td className="py-2 text-right mono font-bold" style={{ color: col }}>{chute.utilization}%</td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                </div>
              </div>
            )}

            {activeTab === 'stats' && (
              <div className="w-full h-full overflow-y-auto space-y-4 px-1 pt-2">
                {/* Telemetry Block */}
                <div className="bg-[var(--panel)] border border-white/10 border-t-2 border-t-[var(--accent)] rounded-lg p-4 shadow-xl">
                  <h3 className="disp text-xs tracking-[0.14em] pb-3 mb-3 border-b border-[var(--line)] text-[var(--accent)]">TÌNH TRẠNG VẬN HÀNH</h3>
                  <div className="grid grid-cols-2 gap-3">
                    <div className="p-3 text-center bg-[#101622]/30 rounded-md">
                      <div className="mono text-[9px] text-[var(--muted)] mb-1">TỔNG ĐƠN HÀNG</div>
                      <div className="disp font-extrabold text-xl text-[var(--cyan)]">{totalOrders.toLocaleString()}</div>
                    </div>
                    <div className="p-3 text-center bg-[#101622]/30 rounded-md">
                      <div className="mono text-[9px] text-[var(--muted)] mb-1">TỔNG TRỌNG LƯỢNG</div>
                      <div className="disp font-extrabold text-xl text-[var(--green)]">
                        {totalWeight.toLocaleString()} kg
                      </div>
                    </div>
                  </div>
                </div>

                {/* Operational Stats */}
                <div className="bg-[var(--panel)] border border-white/10 border-t-2 border-t-[var(--accent)] rounded-lg p-4 shadow-xl">
                  <h3 className="disp text-xs tracking-[0.14em] pb-3 mb-3 border-b border-[var(--line)] text-[var(--accent)]">THỐNG KÊ CHI TIẾT</h3>
                  <div className="space-y-3">
                    {[
                      [displayUtilizationLabel, `${utilTotal}%`, 'var(--cyan)'],
                      ['CÒN TRỐNG', `${free}`, 'var(--green)'],
                      ['Ô ĐANG DÙNG', `${usedCells}/${CHUTE_RACKS.length}`, '#fff']
                    ].map(([label, val, col]) => (
                      <div key={label} className="flex justify-between items-center text-xs text-[var(--muted)] border-b border-[#1e2942]/50 pb-2">
                        <span>{label}</span>
                        <span className="mono font-bold text-sm" style={{color: col}}>{val}</span>
                      </div>
                    ))}
                    <div className="h-1.5 rounded bg-[var(--line)] overflow-hidden">
                      <div className="h-full bg-gradient-to-r from-[var(--green)] to-[var(--cyan)] transition-all duration-1000"
                           style={{width:`${Math.min(100,Number(utilTotal))}%`}}/>
                    </div>
                  </div>
                </div>

                {/* Zone Metrics Blocks */}
                <div className="bg-[var(--panel)] border border-white/10 border-t-2 border-t-[var(--cyan)] rounded-lg p-4 shadow-xl">
                  <h3 className="disp text-xs tracking-[0.14em] pb-3 mb-3 border-b border-[var(--line)] text-[var(--cyan)]">THỐNG KÊ PHÂN KHU (ZONES)</h3>
                  <div className="space-y-4">
                    {[3, 2, 1].map(zoneNum => {
                      const zInfo = getZoneInfo(zoneNum);
                      const colors: Record<number, string> = {
                        1: 'var(--orange)',
                        2: 'var(--yellow)',
                        3: 'var(--green)'
                      };
                      const zColor = colors[zoneNum] || 'var(--cyan)';
                      return (
                        <div key={zoneNum} className="p-3 bg-[#101622]/40 rounded-md border border-white/5"
                             style={{ borderColor: `${zColor}22` }}>
                          <div className="flex justify-between items-center border-b border-[#1e2942]/50 pb-2 mb-2">
                            <span className="disp font-extrabold text-[11px]" style={{ color: zColor }}>ZONE {zoneNum}</span>
                            <span className="mono text-[11px] font-bold" style={{ color: zColor }}>{zInfo.ratio}% sản lượng</span>
                          </div>
                          <div className="grid grid-cols-2 gap-2 text-[10px] text-[var(--muted)]">
                            <div>Bưu cục có hàng: <b className="text-white mono">{zInfo.activeChutesCount}/{zInfo.totalChutes}</b></div>
                            <div>Tổng lượng đơn: <b className="text-white mono">{zInfo.zoneOrders.toLocaleString()}</b></div>
                            <div className="col-span-2 mt-1 border-t border-white/5 pt-1">Tổng trọng lượng: <b className="text-white mono">{zInfo.zoneWeight.toLocaleString()} kg</b></div>
                          </div>
                        </div>
                      );
                    })}
                  </div>
                </div>
              </div>
            )}
          </div>

          {/* Bottom Navigation Bar */}
          <div className="mobile-nav">
            <div className={`mobile-nav-item ${activeTab === 'layout' ? 'active' : ''}`} onClick={() => setActiveTab('layout')}>
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M3 9l9-7 9 7v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/><polyline points="9 22 9 12 15 12 15 22"/></svg>
              <span>Sơ đồ</span>
            </div>
            <div className={`mobile-nav-item ${activeTab === 'top10' ? 'active' : ''}`} onClick={() => setActiveTab('top10')}>
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><circle cx="12" cy="8" r="7"/><polyline points="8.21 13.89 7 23 12 20 17 23 15.79 13.88"/></svg>
              <span>Top 10</span>
            </div>
            <div className={`mobile-nav-item ${activeTab === 'stats' ? 'active' : ''}`} onClick={() => setActiveTab('stats')}>
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><line x1="18" y1="20" x2="18" y2="10"/><line x1="12" y1="20" x2="12" y2="4"/><line x1="6" y1="20" x2="6" y2="14"/></svg>
              <span>Thống kê</span>
            </div>
          </div>
        </>
      )}

      {/* ── Critical Alert Ticker ── */}
      <div className="absolute bottom-0 left-0 right-0 h-8 bg-[var(--accent)] text-[#0a0e14] flex items-center z-30 mono font-bold text-[12px] tracking-[0.05em] overflow-hidden">
        <div className="bg-[#0a0e14] text-[var(--accent)] px-4 h-full flex items-center shrink-0 z-10 font-bold border-r border-[var(--accent)]">
          ● CRITICAL ALERT
        </div>
        <div className="ticker-track">{tickerText}</div>
      </div>
    </div>
  );
}

