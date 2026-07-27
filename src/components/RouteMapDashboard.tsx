import { useEffect, useRef, useState } from 'react';

// Master Database of Post Offices for Map
const POST_OFFICES: Record<string, any> = {
  "HCM_HUB": { "id": "HCM_HUB", "name": "HCM HUB", "province": "HCM", "lat": 10.8433156, "lng": 106.5133537, "poType": "HUB CENTER", "distToHub": 0, "timeToHubMins": 0 },
  "BN_HUB": { "id": "BN_HUB", "name": "BN HUB", "province": "BN", "lat": 21.1280656, "lng": 106.0980148, "poType": "Linehaul", "distToHub": 1792.9, "timeToHubMins": 2138 },
  "AG_CAN_DANG": { "id": "AG_CAN_DANG", "name": "AG CẦN ĐĂNG", "province": "AG", "lat": 10.459212, "lng": 105.297136, "poType": "Linehaul", "distToHub": 180, "timeToHubMins": 281 },
  "AG_LONG_XUYEN": { "id": "AG_LONG_XUYEN", "name": "AG LONG XUYÊN", "province": "AG", "lat": 10.441793, "lng": 105.38603, "poType": "Linehaul", "distToHub": 193, "timeToHubMins": 270 },
  "AG_AN_PHU": { "id": "AG_AN_PHU", "name": "AG AN PHÚ", "province": "AG", "lat": 10.906398, "lng": 105.079943, "poType": "Linehaul", "distToHub": 220, "timeToHubMins": 305 },
  "AG_TAN_CHAU": { "id": "AG_TAN_CHAU", "name": "AG TÂN CHÂU", "province": "AG", "lat": 10.495838, "lng": 105.497569, "poType": "Linehaul", "distToHub": 170, "timeToHubMins": 252 },
  "BD_DI_AN": { "id": "BD_DI_AN", "name": "BD DĨ AN", "province": "BD", "lat": 10.9038, "lng": 106.7725, "poType": "Shuttle", "distToHub": 35, "timeToHubMins": 65 },
  "BD_BINH_HOA": { "id": "BD_BINH_HOA", "name": "BD BÌNH HÒA", "province": "BD", "lat": 10.9523, "lng": 106.7081, "poType": "Shuttle", "distToHub": 30, "timeToHubMins": 58 },
  "LA_TAN_AN": { "id": "LA_TAN_AN", "name": "LA TÂN AN", "province": "LA", "lat": 10.54905, "lng": 106.393869, "poType": "Shuttle", "distToHub": 48, "timeToHubMins": 78 },
  "LA_BEN_LUC": { "id": "LA_BEN_LUC", "name": "LA BẾN LỨC", "province": "LA", "lat": 10.664663, "lng": 106.482608, "poType": "Shuttle", "distToHub": 33, "timeToHubMins": 52 },
  "CT_NINH_KIEU": { "id": "CT_NINH_KIEU", "name": "CT NINH KIỀU", "province": "CT", "lat": 10.023629, "lng": 105.787263, "poType": "Linehaul", "distToHub": 167, "timeToHubMins": 220 },
  "VT_VUNG_TAU": { "id": "VT_VUNG_TAU", "name": "VT VŨNG TÀU", "province": "VT", "lat": 10.4851, "lng": 107.1825, "poType": "Linehaul", "distToHub": 115, "timeToHubMins": 165 }
};

const PROVINCE_COLORS: Record<string, string> = {
  SG: '#00b050', AG: '#ef4444', BD: '#ff5722', CT: '#eab308', ST: '#10b981',
  DT: '#06b6d4', LA: '#00b050', VL: '#8b5cf6', TG: '#ec4899', VT: '#14b8a6',
  BN: '#ff5722', HCM: '#00b050'
};

const COMBINED_ROUTES = [
  { code: 'Round01-AG-AG-HCM', type: 'ghep', mode: 'Linehaul', name: 'Tuyến ghép An Giang - Châu Thành & Long Xuyên', stops: ['AG_CAN_DANG', 'AG_LONG_XUYEN', 'HCM_HUB'], realDistance: 178, stopPenalty: 30, totalEtaDuration: 243 },
  { code: 'Round02-AG-AG-HCM', type: 'ghep', mode: 'Linehaul', name: 'Tuyến ghép An Giang - An Phú & Tân Châu', stops: ['AG_AN_PHU', 'AG_TAN_CHAU', 'HCM_HUB'], realDistance: 228, stopPenalty: 30, totalEtaDuration: 332 },
  { code: 'Round04-BD-BD-HCM', type: 'ghep', mode: 'Shuttle', name: 'Tuyến ghép Bình Dương - Dĩ An & Bình Hòa', stops: ['BD_DI_AN', 'BD_BINH_HOA', 'HCM_HUB'], realDistance: 50, stopPenalty: 30, totalEtaDuration: 96 },
  { code: 'Round09-LA-LA-HCM', type: 'ghep', mode: 'Shuttle', name: 'Tuyến ghép Long An - Tân An & Bến Lức', stops: ['LA_TAN_AN', 'LA_BEN_LUC', 'HCM_HUB'], realDistance: 62, stopPenalty: 30, totalEtaDuration: 118 }
];

const SINGLE_ROUTES = [
  { code: 'Round_LINEHAUL_BN_HCM', type: 'don', mode: 'Linehaul', name: 'Tuyến Linehaul Bắc Nam: BN HUB ➔ HCM HUB', stops: ['BN_HUB', 'HCM_HUB'], realDistance: 1792.9, stopPenalty: 0, totalEtaDuration: 2138 }
];

const ALL_ROUTES = [...COMBINED_ROUTES, ...SINGLE_ROUTES];

function formatDuration(mins: number) {
  if (!mins || mins <= 0) return '0 phút';
  const h = Math.floor(mins / 60);
  const m = mins % 60;
  if (h > 0) return `${h}h ${m}m`;
  return `${m} phút`;
}

export default function RouteMapDashboard() {
  const mapRef = useRef<HTMLDivElement>(null);
  const mapInstanceRef = useRef<any>(null);
  const [selectedRoute, setSelectedRoute] = useState<any>(null);
  const [selectedPO, setSelectedPO] = useState<any>(null);
  const [activeTab, setActiveTab] = useState('ghep');
  const [searchQuery, setSearchQuery] = useState('');

  useEffect(() => {
    if (!mapRef.current || mapInstanceRef.current) return;

    // Dynamically load Leaflet JS & CSS if not already available
    const loadLeaflet = async () => {
      if (!(window as any).L) {
        if (!document.getElementById('leaflet-css-cdn')) {
          const link = document.createElement('link');
          link.id = 'leaflet-css-cdn';
          link.rel = 'stylesheet';
          link.href = 'https://unpkg.com/leaflet@1.9.4/dist/leaflet.css';
          document.head.appendChild(link);
        }

        if (!document.getElementById('leaflet-js-cdn')) {
          const script = document.createElement('script');
          script.id = 'leaflet-js-cdn';
          script.src = 'https://unpkg.com/leaflet@1.9.4/dist/leaflet.js';
          script.onload = () => initMap();
          document.body.appendChild(script);
          return;
        }
      }
      initMap();
    };

    const initMap = () => {
      const L = (window as any).L;
      if (!L || !mapRef.current) return;

      const map = L.map(mapRef.current, {
        center: [10.8433, 106.5133],
        zoom: 8,
        zoomControl: false
      });

      L.control.zoom({ position: 'topright' }).addTo(map);

      L.tileLayer('https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png', {
        attribution: '&copy; OpenStreetMap &copy; CARTO',
        subdomains: 'abcd',
        maxZoom: 19
      }).addTo(map);

      mapInstanceRef.current = map;

      // Render Markers
      Object.values(POST_OFFICES).forEach((po: any) => {
        const isHub = po.id === 'HCM_HUB';
        const color = isHub ? '#00b050' : (PROVINCE_COLORS[po.province] || '#00b050');

        const customIcon = L.divIcon({
          className: 'custom-leaflet-marker',
          html: isHub ? `<div style="width:22px;height:22px;background:#00b050;border:3px solid #fff;border-radius:50%;box-shadow:0 0 16px #00b050;"></div>`
                       : `<div style="width:14px;height:14px;background:${color};border:2px solid #fff;border-radius:50%;"></div>`,
          iconSize: [22, 22],
          iconAnchor: [11, 11]
        });

        const marker = L.marker([po.lat, po.lng], { icon: customIcon });

        marker.on('click', () => {
          setSelectedPO(po);
          setSelectedRoute(null);
        });

        marker.addTo(map);
      });

      // Render Polylines
      ALL_ROUTES.forEach((route: any) => {
        const latLngs = route.stops.map((id: string) => POST_OFFICES[id] ? [POST_OFFICES[id].lat, POST_OFFICES[id].lng] : null).filter(Boolean);
        if (latLngs.length < 2) return;

        const firstPo = POST_OFFICES[route.stops[0]];
        const color = PROVINCE_COLORS[firstPo ? firstPo.province : 'SG'] || '#00b050';

        const polyline = L.polyline(latLngs, {
          color: color,
          weight: route.type === 'ghep' ? 4 : 3,
          opacity: 0.85
        });

        polyline.on('click', () => {
          setSelectedRoute(route);
          setSelectedPO(null);
        });

        polyline.addTo(map);
      });
    };

    loadLeaflet();

    return () => {
      if (mapInstanceRef.current) {
        mapInstanceRef.current.remove();
        mapInstanceRef.current = null;
      }
    };
  }, []);

  return (
    <div className="flex w-full h-[calc(100vh-64px)] bg-[#121316] text-white font-sans overflow-hidden">
      {/* Left Navigation Sidebar */}
      <div className="w-[380px] min-w-[380px] h-full bg-[#18191c] border-r border-white/10 flex flex-col z-20">
        <div className="p-4 bg-[#141518] border-b border-white/10 flex items-center justify-between">
          <div>
            <div className="inline-flex items-center gap-1.5 bg-[#00b050] px-2.5 py-1 rounded-md mb-1 text-xs font-bold">
              <span>J&amp;T</span> <span className="font-normal">Cargo</span>
            </div>
            <h2 className="text-base font-bold text-white">BẢN ĐỒ VẬN TẢI INBOUND</h2>
            <p className="text-xs text-slate-400">Mạng lưới Bưu Cục ➔ HCM HUB</p>
          </div>
        </div>

        <div className="p-3 border-b border-white/10">
          <input
            type="text"
            placeholder="Tìm mã tuyến, bưu cục..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="w-full px-3 py-2 bg-white/5 border border-white/10 rounded-lg text-sm outline-none focus:border-[#00b050]"
          />
        </div>

        <div className="flex p-2 gap-2 bg-black/20">
          <button onClick={() => setActiveTab('ghep')} className={`flex-1 py-1.5 text-xs font-semibold rounded-md ${activeTab === 'ghep' ? 'bg-[#00b050]/20 text-[#00b050] border border-[#00b050]/40' : 'text-slate-400'}`}>Tuyến Ghép</button>
          <button onClick={() => setActiveTab('don')} className={`flex-1 py-1.5 text-xs font-semibold rounded-md ${activeTab === 'don' ? 'bg-[#ff5722]/20 text-[#ff5722] border border-[#ff5722]/40' : 'text-slate-400'}`}>Tuyến Đơn</button>
        </div>

        <div className="flex-1 overflow-y-auto p-3 flex flex-col gap-2">
          {ALL_ROUTES.filter(r => activeTab === 'all' || r.type === activeTab).map(route => (
            <div
              key={route.code}
              onClick={() => { setSelectedRoute(route); setSelectedPO(null); }}
              className={`p-3 rounded-lg border transition cursor-pointer ${selectedRoute?.code === route.code ? 'bg-[#00b050]/20 border-[#00b050]' : 'bg-white/5 border-white/10 hover:bg-white/10'}`}
            >
              <div className="flex justify-between items-center mb-1">
                <span className="font-bold text-sm text-[#00b050]">{route.code}</span>
                <span className="text-[10px] px-2 py-0.5 rounded bg-[#00b050]/20 text-[#00b050] border border-[#00b050]/30">{route.mode}</span>
              </div>
              <div className="text-xs text-slate-300 mb-1">{route.stops.map(id => POST_OFFICES[id]?.name || id).join(' ➔ ')}</div>
              <div className="text-[11px] text-amber-400">⏱️ ETA Vận Hành: {formatDuration(route.totalEtaDuration)} ({route.realDistance} km)</div>
            </div>
          ))}
        </div>
      </div>

      {/* Main Map Viewport */}
      <div className="flex-1 h-full relative">
        <div ref={mapRef} className="w-full h-full" />

        {/* Floating Lockable Detail Card (Bottom-Right) */}
        {(selectedRoute || selectedPO) && (
          <div className="absolute bottom-6 right-6 w-[360px] bg-[#18191c]/95 backdrop-blur-md border border-[#00b050]/50 rounded-xl p-4 shadow-2xl z-[1000]">
            <div className="flex justify-between items-center border-b border-white/10 pb-2 mb-3">
              <span className={`text-xs font-bold px-2 py-0.5 rounded ${selectedPO?.id === 'HCM_HUB' ? 'bg-[#00b050] text-white' : 'bg-[#00b050]/20 text-[#00b050] border border-[#00b050]/40'}`}>
                {selectedPO ? (selectedPO.id === 'HCM_HUB' ? 'HUB CENTER' : selectedPO.poType) : selectedRoute.mode}
              </span>
              <h4 className="font-bold text-[#00b050]">{selectedPO ? selectedPO.name : selectedRoute.code}</h4>
              <button onClick={() => { setSelectedRoute(null); setSelectedPO(null); }} className="text-slate-400 hover:text-white text-base">✕</button>
            </div>

            {selectedPO ? (
              <div className="grid grid-cols-2 gap-2 text-xs">
                <div className="bg-white/5 p-2 rounded border border-white/10">
                  <div className="text-slate-400 text-[10px]">Khoảng Cách Về HUB</div>
                  <div className="font-bold text-emerald-400">{selectedPO.distToHub} km</div>
                </div>
                <div className="bg-white/5 p-2 rounded border border-white/10">
                  <div className="text-slate-400 text-[10px]">Thời Gian Di Chuyển</div>
                  <div className="font-bold text-amber-400">{formatDuration(selectedPO.timeToHubMins)}</div>
                </div>
                <div className="bg-white/5 p-2 rounded border border-white/10 text-slate-500 italic">Volume: (Chưa có dữ liệu)</div>
                <div className="bg-white/5 p-2 rounded border border-white/10 text-slate-500 italic">Thời gian xuất phát: (Chưa có dữ liệu)</div>
                <div className="col-span-2 bg-white/5 p-2 rounded border border-white/10 text-slate-500 italic">Thời gian dự kiến đến: (Chưa có dữ liệu)</div>
              </div>
            ) : (
              <div className="grid grid-cols-2 gap-2 text-xs">
                <div className="bg-white/5 p-2 rounded border border-white/10">
                  <div className="text-slate-400 text-[10px]">Quãng Đường</div>
                  <div className="font-bold text-emerald-400">{selectedRoute.realDistance} km</div>
                </div>
                <div className="bg-white/5 p-2 rounded border border-white/10">
                  <div className="text-slate-400 text-[10px]">Dừng Ghép</div>
                  <div className="font-bold text-amber-400">+{selectedRoute.stopPenalty}m</div>
                </div>
                <div className="col-span-2 bg-[#00b050]/10 p-2.5 rounded border border-[#00b050]/30">
                  <div className="text-[#00b050] text-[10px] font-bold">TỔNG ETA VẬN HÀNH THỰC TẾ</div>
                  <div className="font-bold text-amber-400 text-base">{formatDuration(selectedRoute.totalEtaDuration)}</div>
                </div>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
