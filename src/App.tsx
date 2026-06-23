import { useState, useEffect } from 'react';

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
  { areaId: 'B15', name: 'SG TÂN HƯNG', zone: 2 },       { areaId: 'B16', name: 'SG ĐÔNG THẠNH', zone: 2 },
  { areaId: 'B17', name: 'BD DĨ AN', zone: 2 },          { areaId: 'B18', name: 'SG KHÁNH HỘI', zone: 2 }
];

const ZONE2_TRUCKS = Array.from({ length: 23 }, (_, i) => ({
  areaId: `T2-${String(23 - i).padStart(2, '0')}`,
  name: `TẢI Chờ 2-${String(23 - i).padStart(2, '0')}`,
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

const CHUTE_RACKS = [...ZONE3_LIST, ...ZONE2_LIST, ...ZONE1_LIST];
const ALL_RACKS = [...CHUTE_RACKS, ...ZONE3_TRUCKS, ...ZONE2_TRUCKS];

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

async function fetchSheetData() {
  try {
    const response = await fetch('https://docs.google.com/spreadsheets/d/1GMgvwa1MIEg0P102MDBcvwJPd-0wAeZh3hewmz_LBQI/export?format=csv&gid=0');
    if (!response.ok) throw new Error('Network response was not ok');
    const csvText = await response.text();
    const lines = csvText.split('\n');
    const sheetData: Record<string, { buuCuc: string, volume: number, capacity: number }> = {};
    
    for (let i = 1; i < lines.length; i++) {
      const line = lines[i].trim();
      if (!line) continue;
      
      const parts = line.split(',');
      if (parts.length < 4) continue;
      
      const zone = parts[0].trim().replace(/^"|"$/g, '');
      const areaId = parts[1].trim().replace(/^"|"$/g, '');
      const buuCuc = parts[2].trim().replace(/^"|"$/g, '');
      const volumeStr = parts[3].trim().replace(/^"|"$/g, '');
      const capacityStr = parts[7] ? parts[7].trim().replace(/^"|"$/g, '') : '780';
      
      const volume = volumeStr.trim() !== '' ? parseInt(volumeStr, 10) : NaN;
      const capacity = capacityStr.trim() !== '' ? parseInt(capacityStr, 10) : 780;
      
      if (areaId && zone) {
        const key = `${zone}_${areaId}`;
        sheetData[key] = {
          buuCuc,
          volume: isNaN(volume) ? -1 : volume,
          capacity: isNaN(capacity) ? 780 : capacity
        };
      }
    }
    return sheetData;
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

function ZoneCell({ c, d, bx, by, bw, bh, midLabelY, isHovered, onEnter, onLeave, addCenterLine, isTruck }:
  { c:any, d:any, bx:number, by:number, bw:number, bh:number, midLabelY:number,
    isHovered:boolean, onEnter:()=>void, onLeave:()=>void, addCenterLine?:boolean, isTruck?:boolean }) {
  const col = isTruck ? 'rgba(255,255,255,0.2)' : (UTILCOL[d.bucket] || '#374151');
  const fillH = (bh - 2) * Math.min(d.utilization, 110) / 110;
  return (
    <g onMouseEnter={onEnter} onMouseLeave={onLeave} className="cursor-pointer">
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
  const [data,       setData]       = useState<any>(generateMockData());
  const [utilTotal,  setUtilTotal]  = useState('0.0');
  const [free,       setFree]       = useState(0);
  const [usedCells,  setUsedCells]  = useState(0);
  const [totalOrders,setTotalOrders]= useState(0);
  const [over,       setOver]       = useState(0);
  const [hoveredRack,setHoveredRack]= useState<any>(null);
  const [tickerText, setTickerText] = useState('HỆ THỐNG ỔN ĐỊNH — KHÔNG CÓ CẢNH BÁO');
  const [loading,    setLoading]    = useState(false);
  const [hoveredZone,setHoveredZone] = useState<number | null>(null);

  const fetchAndUpdateData = async () => {
    setLoading(true);
    const sheetData = await fetchSheetData();
    
    // Cập nhật tên bưu cục realtime từ sheet
    if (sheetData) {
      const updateListName = (list: any[]) => {
        list.forEach(item => {
          const key = `${item.zone}_${item.areaId}`;
          if (sheetData[key] && sheetData[key].buuCuc) {
            item.name = sheetData[key].buuCuc;
          } else {
            // Reset to Dự phòng if not in sheet
            item.name = `${item.areaId} Dự phòng`;
          }
        });
      };
      updateListName(ZONE3_LIST);
      updateListName(ZONE2_LIST);
      updateListName(ZONE1_LIST);
    }

    const newData = ALL_RACKS.reduce((acc, curr: any) => {
      let capacity = 780;
      let current = 0;
      let util = 0;
      let isMocked = true;

      const key = curr.zone ? `${curr.zone}_${curr.areaId}` : null;

      if (key && sheetData) {
        if (sheetData[key]) {
          const item = sheetData[key];
          capacity = item.capacity;
          if (item.volume !== -1) {
            current = item.volume;
            util = Math.floor((current / capacity) * 100);
            isMocked = false;
          } else {
            current = 0;
            util = 0;
            isMocked = false;
          }
        } else {
          // Spare chute not in sheet
          current = 0;
          util = 0;
          isMocked = false;
        }
      }

      // Fallback sinh ngẫu nhiên nếu không có dữ liệu thực tế (chỉ cho bãi xe tải/dự phòng khi sheetData null)
      if (isMocked) {
        if (!curr.zone || !sheetData) {
          util = Math.floor(Math.random() * 110);
          current = Math.floor(capacity * (util / 100));
        } else {
          current = 0;
          util = 0;
        }
      }

      let bucket = 'green';
      if (util > 100) bucket = 'darkred';
      else if (util >= 95) bucket = 'red';
      else if (util >= 80) bucket = 'orange';
      else if (util >= 50) bucket = 'yellow';

      acc[curr.areaId] = {
        current,
        capacity,
        remaining: Math.max(0, capacity - current),
        utilization: util,
        bucket,
        name: curr.name
      };
      return acc;
    }, {} as any);

    setData(newData);
    setLoading(false);
  };

  const getZoneInfo = (zone: number) => {
    let activeChutesCount = 0;
    let zoneOrders = 0;
    const zoneChutes = CHUTE_RACKS.filter(c => c.zone === zone);
    
    zoneChutes.forEach(c => {
      const d = data[c.areaId];
      if (d) {
        zoneOrders += d.current;
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
      ratio
    };
  };

  const getTop10Chutes = () => {
    return CHUTE_RACKS.map(c => {
      const d = data[c.areaId] || { current: 0, capacity: 780, utilization: 0, bucket: 'green', name: c.name };
      return {
        areaId: c.areaId,
        name: d.name || c.name,
        current: d.current,
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

  useEffect(() => {
    fetchAndUpdateData();
  }, []);

  useEffect(() => {
    let tCap=0, tCur=0, tRem=0, tOver=0, tUsed=0;
    const alerts: string[] = [];
    CHUTE_RACKS.forEach(c => {
      const d = data[c.areaId]; if (!d) return;
      tCap += d.capacity; tCur += d.current; tRem += d.remaining;
      if (d.current > 0) tUsed++;
      if (d.utilization > 100) { tOver++; alerts.push(`${c.areaId} VƯỢT SỨC CHỨA (${d.utilization}%)`); }
      else if (d.utilization >= 95) alerts.push(`${c.areaId} SẮP ĐẦY (${d.utilization}%)`);
    });
    setUtilTotal((tCap ? (tCur/tCap)*100 : 0).toFixed(1));
    setFree(tRem); setUsedCells(tUsed); setTotalOrders(tCur); setOver(tOver);
    setTickerText(alerts.length > 0
      ? alerts.join(' // ') + ' // ' + alerts.join(' // ')
      : `HỆ THỐNG ỔN ĐỊNH — KHÔNG CÓ CẢNH BÁO // TỔNG ${tCur} ĐƠN HÀNG // LẤP ĐẦY ${(tCap?(tCur/tCap)*100:0).toFixed(1)}%`
    );
  }, [data]);

  return (
    <div className="w-full h-full relative font-sans text-white bg-[#0a0e14]">
      <div className="absolute top-0 left-0 right-0 h-12 flex items-center justify-between px-6 z-20"
           style={{background:'linear-gradient(180deg,rgba(10,14,20,.95),rgba(10,14,20,0))'}}>
        <div className="flex items-center gap-3 select-none">
          {/* Logo J&T Cargo */}
          <svg width="120" height="30" viewBox="0 0 135 50" fill="none" xmlns="http://www.w3.org/2000/svg" className="h-8 w-auto">
            {/* Green background matching the attached image */}
            <rect width="135" height="50" rx="6" fill="#006a38" />
            <g transform="skewX(-16) translate(6, 2)">
              {/* J */}
              <path d="M 28,10 H 20 V 32 H 5 V 37 H 28 Z" fill="#ffffff" />
              {/* & */}
              <text x="29" y="33" fill="#ffffff" fontSize="20" fontWeight="950" fontFamily="'Arial', sans-serif">{"&"}</text>
              {/* T */}
              <rect x="52" y="15" width="8" height="22" fill="#ffffff" />
              <rect x="40" y="10" width="32" height="5" fill="#ffffff" />
              <rect x="72" y="10" width="16" height="1.4" fill="#ffffff" />
              <rect x="72" y="11.8" width="11" height="1.4" fill="#ffffff" />
              <rect x="72" y="13.6" width="6" height="1.4" fill="#ffffff" />
              {/* Cargo */}
              <text x="76" y="36" fill="#ffffff" fontSize="18" fontWeight="bold" fontFamily="'Montserrat', 'Arial', sans-serif">Cargo</text>
            </g>
          </svg>
          <div className="h-5 w-px bg-white/20" />
          <div className="disp font-extrabold text-sm tracking-[0.18em] text-white/90"
               style={{textShadow:'0 0 12px rgba(255,255,255,0.1)'}}>HCM HUB</div>
        </div>
        <div className="flex gap-6">
          <div className="mono text-xs text-[var(--muted)]">SYSTEM: <b className="text-[var(--green)]">ONLINE</b></div>
          <div className="mono text-xs text-[var(--muted)]">ZONE: LAT 10.823 • LONG 106.63</div>
        </div>
      </div>

      <div className="absolute z-20 top-16 left-6 w-80 bg-[var(--panel)] border border-white/10 border-t-2 border-t-[var(--accent)] rounded-lg backdrop-blur-md shadow-2xl p-4">
        <h3 className="disp text-xs tracking-[0.14em] pb-3 mb-3 border-b border-[var(--line)] text-[var(--accent)]">OPERATIONAL MONITOR</h3>
        <div className="space-y-3">
          {[['TỈ LỆ LẤP ĐẦY', `${utilTotal}%`, 'var(--cyan)'],
            ['CÒN TRỐNG', `${free}`, 'var(--green)'],
            ['Ô ĐANG DÙNG', `${usedCells}/${CHUTE_RACKS.length}`, '#fff']
          ].map(([label, val, col]) => (
            <div key={label as string} className="flex justify-between items-center text-[13px] text-[var(--muted)] border-b border-[#1e2942]/50 pb-2">
              <span>{label}</span>
              <span className="mono font-bold text-[15px]" style={{color: col as string}}>{val}</span>
            </div>
          ))}
          <div className="h-1.5 rounded bg-[var(--line)] overflow-hidden">
            <div className="h-full bg-gradient-to-r from-[var(--green)] to-[var(--cyan)] transition-all duration-1000"
                 style={{width:`${Math.min(100,Number(utilTotal))}%`}}/>
          </div>
        </div>
        <div className="mt-5 pt-4 border-t border-[var(--line)]">
          <h4 className="disp text-[10px] tracking-[0.12em] text-[var(--muted)] mb-3">CHI TIẾT Ô CHỨA</h4>
          {hoveredRack ? (
            <div className="space-y-2 bg-[#101622]/60 rounded-md p-3 border border-white/5">
              {[['Mã ô', hoveredRack.areaId,'var(--cyan)'],
                ['Tên', hoveredRack.name, '#fff'],
                ['Số lượng', `${hoveredRack.current}/${hoveredRack.capacity} Đơn hàng`, '#fff'],
                ['% Lấp đầy', `${hoveredRack.utilization}%`, UTILCOL[hoveredRack.bucket]]
              ].map(([k,v,c]) => (
                <div key={k as string} className="flex justify-between">
                  <span className="text-[11px] text-[var(--muted)]">{k}:</span>
                  <span className="mono text-[11px] font-bold truncate max-w-[150px]" style={{color:c as string}}>{v}</span>
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

      <div className="absolute z-20 top-[390px] left-6 w-80 bg-[var(--panel)] border border-white/10 border-t-2 border-t-[var(--accent)] rounded-lg backdrop-blur-md shadow-2xl p-4">
        <h3 className="disp text-xs tracking-[0.14em] pb-3 mb-2 border-b border-[var(--line)] text-[var(--accent)]">TOP 10 BƯU CỤC TỒN HÀNG</h3>
        <div className="overflow-x-auto">
          <table className="w-full text-left border-collapse">
            <thead>
              <tr className="border-b border-[var(--line)] text-[10px] text-[var(--muted)] uppercase mono font-bold">
                <th className="py-1 w-8">#</th>
                <th className="py-1 w-12">Mã</th>
                <th className="py-1">Bưu Cục</th>
                <th className="py-1 text-right w-16">Lượng tồn</th>
                <th className="py-1 text-right w-12">% Lấp đầy</th>
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
                    <td className="py-1 truncate max-w-[110px] font-medium text-white/95" title={chute.name}>
                      {chute.name}
                    </td>
                    <td className="py-1 text-right mono font-bold text-white">{chute.current.toLocaleString()}</td>
                    <td className="py-1 text-right mono font-bold" style={{ color: col }}>{chute.utilization}%</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </div>

      <div className="absolute z-20 top-16 right-6 w-60 bg-[var(--panel)] border border-white/10 border-t-2 border-t-[var(--accent)] rounded-lg backdrop-blur-md shadow-2xl p-4">
        <h3 className="disp text-xs tracking-[0.14em] pb-3 mb-2 border-b border-[var(--line)] text-[var(--accent)]">REAL-TIME TELEMETRY</h3>
        <div className="space-y-4">
          <div className="p-3 text-center border-b border-[var(--line)] bg-[#101622]/30 rounded-md">
            <div className="mono text-[10px] tracking-[0.12em] text-[var(--muted)] mb-1">TỔNG ĐƠN HÀNG</div>
            <div className="disp font-extrabold text-3xl text-[var(--cyan)]">{totalOrders.toLocaleString()}</div>
            <div className="mono text-[9px] tracking-[0.1em] text-[var(--muted)] mt-1">ĐƠN HÀNG / KHO</div>
          </div>
          <div className="p-3 text-center bg-[#101622]/30 rounded-md">
            <div className="mono text-[10px] tracking-[0.12em] text-[var(--muted)] mb-1">Ô QUÁ TẢI</div>
            <div className="disp font-extrabold text-3xl" style={{color:over>0?'var(--red)':'var(--green)'}}>
              {over.toString().padStart(2,'0')}
            </div>
            <div className="mono text-[9px] tracking-[0.1em] text-[var(--muted)] mt-1">FLEET MATRIX</div>
          </div>
        </div>
      </div>

      <div className="absolute z-20 top-[335px] right-6 w-60 bg-[var(--panel)] border border-white/10 border-t-2 border-t-[var(--cyan)] rounded-lg backdrop-blur-md shadow-2xl p-4">
        <h3 className="disp text-xs tracking-[0.14em] pb-3 mb-2 border-b border-[var(--line)] text-[var(--cyan)]">ZONE METRICS</h3>
        {hoveredZone !== null ? (
          (() => {
            const zInfo = getZoneInfo(hoveredZone);
            return (
              <div className="space-y-3">
                <div className="flex justify-between items-center text-[12px] text-[var(--muted)] border-b border-[#1e2942]/50 pb-2">
                  <span>Phân khu</span>
                  <span className="disp font-extrabold text-[14px] text-[var(--cyan)]">ZONE {zInfo.zone}</span>
                </div>
                <div className="flex justify-between items-center text-[12px] text-[var(--muted)] border-b border-[#1e2942]/50 pb-2">
                  <span>Bưu cục có hàng</span>
                  <span className="mono font-bold text-[13px] text-white">{zInfo.activeChutesCount} / {zInfo.totalChutes}</span>
                </div>
                <div className="flex justify-between items-center text-[12px] text-[var(--muted)] border-b border-[#1e2942]/50 pb-2">
                  <span>Tổng lượng đơn</span>
                  <span className="mono font-bold text-[13px] text-white">{zInfo.zoneOrders.toLocaleString()}</span>
                </div>
                <div className="flex justify-between items-center text-[12px] text-[var(--muted)] border-b border-[#1e2942]/50 pb-2">
                  <span>Tỉ lệ chứa hàng</span>
                  <span className="mono font-bold text-[13px] text-[var(--cyan)]">{zInfo.ratio}%</span>
                </div>
                <div className="h-1.5 rounded bg-[var(--line)] overflow-hidden">
                  <div className="h-full bg-[var(--cyan)] transition-all duration-500"
                       style={{width:`${Math.min(100,Number(zInfo.ratio))}%`}}/>
                </div>
              </div>
            );
          })()
        ) : (
          <div className="text-center py-6 text-[11px] text-[var(--muted)] border border-dashed border-[var(--line)] rounded-md">
            Rê chuột vào ô của Zone để xem chi tiết phân khu
          </div>
        )}
      </div>

      <div className="absolute bottom-16 left-6 z-20 flex gap-3 mono text-[10px] text-[var(--muted)] bg-[var(--panel)] border border-[var(--line)] rounded-lg py-2 px-3 backdrop-blur-md shadow-lg">
        {[['#0c883d','Ô chứa'],['var(--orange)','Cổng Outbound'],
          ['var(--inbound)','Cổng Inbound'],['rgba(100,116,139,0.7)','Xe tải']].map(([c,l])=>(
          <span key={l} className="flex items-center gap-1.5">
            <i className="w-2.5 h-2.5 rounded-sm" style={{background:c}}/>
            {l}
          </span>
        ))}
      </div>

      <button onClick={handleResetZoom}
              className="absolute bottom-16 right-36 z-20 font-sans font-bold text-xs uppercase py-2.5 px-4 rounded-md border border-white/20 bg-[var(--panel)] text-[var(--muted)] cursor-pointer hover:bg-white/10 hover:text-white transition-all shadow-lg">
        THU NHỎ / RESET
      </button>

      <button onClick={fetchAndUpdateData} disabled={loading}
              className="absolute bottom-16 right-6 z-20 reload-pulse font-sans font-bold text-xs uppercase py-2.5 px-4 rounded-md border border-[var(--accent)] bg-[var(--void)] text-[var(--accent)] cursor-pointer hover:bg-[var(--accent)] hover:text-[#0a0e14] transition-all shadow-lg disabled:opacity-50 disabled:cursor-not-allowed">
        {loading ? 'ĐANG ĐỒNG BỘ...' : 'ĐỒNG BỘ'}
      </button>

      <div className="absolute inset-0 flex items-center justify-center pt-10 pb-20 px-6">
        <svg viewBox="0 0 1100 600" className="w-full h-full max-h-[85vh] drop-shadow-2xl select-none"
             onWheel={handleWheel}
             onMouseDown={handleMouseDown}
             onMouseMove={handleMouseMove}
             onMouseUp={handleMouseUp}
             onMouseLeave={handleMouseUp}
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
          <g transform={`translate(${translateX}, ${translateY}) scale(${scale})`} style={{ transformOrigin: '550px 350px' }}>

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
                  fill="none" stroke="var(--cyan)" strokeWidth="1.8" strokeOpacity="0.8" pointerEvents="none"/>
            {/* Zone 3 Chutes Right border (bao quanh C01->C05 - vùng xanh lá) */}
            <rect x={642} y={118} width={140} height={Z_H} rx="2"
                  fill="none" stroke="#22c55e" strokeWidth="1.8" strokeOpacity="0.8" pointerEvents="none"/>
            {/* Zone 3 Trucks border (bao quanh T3-01->T3-24 - vùng xanh dương) */}
            <rect x={110} y={174} width={672} height={Z_H} rx="2"
                  fill="none" stroke="var(--cyan)" strokeWidth="1.8" strokeOpacity="0.8" pointerEvents="none"/>
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
            {/* Zone 2 Chutes Left border (bao quanh B01->B18) */}
            <rect x={138} y={336} width={504} height={Z_H} rx="2"
                  fill="none" stroke="var(--yellow)" strokeWidth="1.8" strokeOpacity="0.8" pointerEvents="none"/>
            {/* Zone 2 Chutes Right border (bao quanh A00->A04 - vùng màu vàng) */}
            <rect x={642} y={336} width={140} height={Z_H} rx="2"
                  fill="none" stroke="#eab308" strokeWidth="1.8" strokeOpacity="0.8" pointerEvents="none"/>
            {/* Zone 2 Trucks border (bao quanh T2-01->T2-23 - vùng đỏ) */}
            <rect x={138} y={280} width={644} height={Z_H} rx="2"
                  fill="none" stroke="var(--red)" strokeWidth="1.8" strokeOpacity="0.8" pointerEvents="none"/>
          </g>

          <line x1={(A23_X + NS_X)/2} y1={EW_Y+EW_H/2} x2={(A23_X + NS_X)/2} y2={EW_Y+3}
                fill="none" stroke="rgba(234,179,8,0.45)" strokeWidth="1.2" markerEnd="url(#arrow)"/>
          <line x1={(A23_X + NS_X)/2} y1={EW_Y+EW_H/2} x2={(A23_X + NS_X)/2} y2={EW_Y+EW_H-3}
                fill="none" stroke="rgba(234,179,8,0.45)" strokeWidth="1.2" markerEnd="url(#arrow)"/>
          <text x={(A23_X + NS_X)/2 + 20} y={EW_Y+EW_H/2+2} textAnchor="middle"
                fill="rgba(234,179,8,0.65)" className="mono text-[5.5px] font-bold">XE TẢI CHỤM ĐẦU</text>

          <g>
            {ZONE1_LIST.map((c, i) => {
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
                               addCenterLine={true}/>;
            })}
            <rect x={220} y={Z1_Y} width={420} height={Z_H} rx="2"
                  fill="none" stroke="var(--orange)" strokeWidth="1.8" strokeOpacity="0.8" pointerEvents="none"/>
            <text x={218} y={Z1_Y-6} fill="rgba(249,115,22,0.7)"
                  className="mono text-[6.5px] font-bold tracking-wide">KHU CHỜ XUẤT TẢI (ZONE 1)</text>
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
              { id: 'A1-A2', x: 110, w: 74, type: 'outbound' },
              { id: 'A3-A4', x: 194, w: 74, type: 'outbound' },
              { id: 'A5', x: 289, w: 25, type: 'outbound' },
              { id: 'A6', x: 335, w: 25, type: 'outbound' },
              { id: 'A7', x: 381, w: 25, type: 'outbound' },
              { id: 'A8', x: 427, w: 25, type: 'outbound' },
              { id: 'A9-A10', x: 473, w: 74, type: 'outbound' },
              { id: 'A11-A12', x: 568, w: 74, type: 'outbound' },
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
          <text x={(WL+WR)/2} y={DOCK_Y+DOCK_H+11} textAnchor="middle"
                fill="var(--muted)" className="font-sans text-[7.5px] tracking-wide">
            A1–A12: Cổng xuất (Outbound) | A13–A18: Cổng nhập hàng (Inbound)
          </text>
          </g>
        </svg>
      </div>

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
