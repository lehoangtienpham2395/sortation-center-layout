import React, { useState, useEffect, useRef } from 'react';
import html2canvas from 'html2canvas';
import * as XLSX from 'xlsx';
import { Camera, FileSpreadsheet, RefreshCw, Clock, CheckCircle2 } from 'lucide-react';
import defaultReceivingData from '../data/inbound_receiving_table.json';

export interface RouteMetric {
  line: string;
  metric1: number; // PCS
  metric2: number; // Tons
  fc_m1?: number;
  fc_m2?: number;
  bl_m1?: number;
  bl_m2?: number;
  tot_m1?: number;
  tot_m2?: number;
}

export interface InboundReceivingTableData {
  updated_at: string;
  op_date: string;
  block1: RouteMetric[];
  block2: RouteMetric[];
  block3: RouteMetric[];
  grand_total: {
    metric1: number;
    metric2: number;
    fc_m1?: number;
    fc_m2?: number;
    bl_m1?: number;
    bl_m2?: number;
    tot_m1?: number;
    tot_m2?: number;
  };
}

export const InboundReceivingReport: React.FC = () => {
  const [data, setData] = useState<InboundReceivingTableData>(defaultReceivingData as InboundReceivingTableData);
  const [loading, setLoading] = useState<boolean>(false);
  const [toastMessage, setToastMessage] = useState<string | null>(null);
  const [nextSyncSeconds, setNextSyncSeconds] = useState<number>(3600); // 1 hour = 3600s
  const captureAreaRef = useRef<HTMLDivElement>(null);

  const showToast = (msg: string) => {
    setToastMessage(msg);
    setTimeout(() => setToastMessage(null), 3500);
  };

  // Fetch / Sync Data
  const fetchData = async (isManual = false) => {
    setLoading(true);
    try {
      const cacheBust = `${Date.now()}_${Math.floor(Math.random() * 100000)}`;
      let fetchedJson: InboundReceivingTableData | null = null;

      // 1. Try local FastAPI / Flask backend if running
      try {
        const res = await fetch(`http://127.0.0.1:8520/api/inbound_receiving_table?t=${cacheBust}`, {
          cache: 'no-store'
        });
        if (res.ok) {
          const apiRes = await res.json();
          if (apiRes && apiRes.data) {
            fetchedJson = apiRes.data;
          }
        }
      } catch {
        // Fallback to local json file
      }

      // 2. Try static public / relative json
      if (!fetchedJson) {
        try {
          const res = await fetch(`data/inbound_receiving_table.json?t=${cacheBust}`, {
            cache: 'no-store'
          });
          if (res.ok) {
            fetchedJson = await res.json();
          }
        } catch {
          // Keep current state
        }
      }

      if (fetchedJson && fetchedJson.grand_total) {
        setData(fetchedJson);
        setNextSyncSeconds(3600);
        if (isManual) {
          showToast('✅ Đã cập nhật dữ liệu mới nhất!');
        }
      } else if (isManual) {
        showToast('ℹ️ Đang hiển thị bản ghi đã lưu gần nhất.');
      }
    } catch (err) {
      console.error('Error fetching receiving table:', err);
      if (isManual) showToast('⚠️ Không thể tải dữ liệu mới.');
    } finally {
      setLoading(false);
    }
  };

  // 1-Hour Auto-Sync Interval (3600 seconds)
  useEffect(() => {
    fetchData();

    // 1-hour interval timer
    const syncInterval = setInterval(() => {
      fetchData();
    }, 3600 * 1000);

    // 1-second countdown display timer
    const countdownInterval = setInterval(() => {
      setNextSyncSeconds(prev => (prev > 1 ? prev - 1 : 3600));
    }, 1000);

    return () => {
      clearInterval(syncInterval);
      clearInterval(countdownInterval);
    };
  }, []);

  // Format MM:SS for countdown
  const formatCountdown = (secs: number) => {
    const m = Math.floor(secs / 60);
    const s = secs % 60;
    return `${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`;
  };

  // Capture Snapshot PNG (Scale 2.5 HD)
  const handleCaptureSnapshot = async () => {
    if (!captureAreaRef.current) return;
    try {
      showToast('📸 Đang kết xuất ảnh báo cáo độ phân giải cao...');
      const cleanTime = (data.updated_at || 'LIVE').replace(/[^a-zA-Z0-9]/g, '_');
      const canvas = await html2canvas(captureAreaRef.current, {
        scale: 2.5,
        useCORS: true,
        backgroundColor: '#FFFFFF',
        logging: false,
        scrollX: 0,
        scrollY: 0
      });

      const link = document.createElement('a');
      link.download = `BaoCao_SanLuong_Nhan_HCMHUB_${cleanTime}.png`;
      link.href = canvas.toDataURL('image/png');
      link.click();
      showToast('🎉 Đã tải ảnh báo cáo chuẩn HD về máy!');
    } catch (err) {
      console.error('Capture error:', err);
      showToast('❌ Lỗi khi chụp ảnh báo cáo.');
    }
  };

  // Export Excel (.xlsx)
  const handleExportExcel = () => {
    try {
      const rows: any[] = [];
      rows.push(['THỐNG KÊ LƯỢNG ĐƠN NHẬN TRONG NGÀY / 每日订单接收量统计报表']);
      rows.push([`Cập nhật / 更新时间: ${data.updated_at}`]);
      rows.push([]);
      rows.push([
        'PHÂN KHỐI / 分块 (BLOCK)',
        'LOẠI TUYẾN / 线路类型 (ROUTE)',
        'SỐ LƯỢNG ĐƠN / KIỆN / 进港件数 (PCS)',
        'TRỌNG LƯỢNG (TẤN) / 重量 (TONS)'
      ]);

      // Grand Total
      rows.push([
        'Σ',
        'TỔNG CỘNG / 合计',
        data.grand_total?.metric1 || 0,
        Number(data.grand_total?.metric2 || 0).toFixed(2)
      ]);

      // Block 1
      (data.block1 || []).forEach((item, idx) => {
        rows.push([
          idx === 0 ? 'Pickup to HUB / 取件进港' : '',
          item.line,
          item.metric1 || 0,
          Number(item.metric2 || 0).toFixed(2)
        ]);
      });

      // Block 2
      (data.block2 || []).forEach((item, idx) => {
        rows.push([
          idx === 0 ? 'LH BN to HUB / 北宁调拨进港' : '',
          item.line,
          item.metric1 || 0,
          Number(item.metric2 || 0).toFixed(2)
        ]);
      });

      // Block 3
      (data.block3 || []).forEach((item, idx) => {
        rows.push([
          idx === 0 ? 'Total / 线路汇总' : '',
          item.line,
          item.metric1 || 0,
          Number(item.metric2 || 0).toFixed(2)
        ]);
      });

      const worksheet = XLSX.utils.aoa_to_sheet(rows);
      // Auto column widths
      worksheet['!cols'] = [{ wch: 32 }, { wch: 25 }, { wch: 28 }, { wch: 22 }];

      const workbook = XLSX.utils.book_new();
      XLSX.utils.book_append_sheet(workbook, worksheet, 'ThongKeNhan');

      const cleanTime = (data.updated_at || 'LIVE').replace(/[^a-zA-Z0-9]/g, '_');
      XLSX.writeFile(workbook, `BaoCao_SanLuong_Nhan_HCMHUB_${cleanTime}.xlsx`);
      showToast('📊 Đã xuất file Excel thành công!');
    } catch (err) {
      console.error('Excel export error:', err);
      showToast('❌ Lỗi khi xuất file Excel.');
    }
  };

  // Helper map for fast lookup
  const b1Map: Record<string, RouteMetric> = {};
  (data.block1 || []).forEach(item => { b1Map[item.line] = item; });

  const b2Map: Record<string, RouteMetric> = {};
  (data.block2 || []).forEach(item => { b2Map[item.line] = item; });

  const b3Map: Record<string, RouteMetric> = {};
  (data.block3 || []).forEach(item => { b3Map[item.line] = item; });

  return (
    <div className="w-full min-h-screen bg-[#0A0E17] text-white p-4 md:p-6 lg:p-8 flex flex-col items-center">
      {/* Toast Alert */}
      {toastMessage && (
        <div className="fixed top-5 right-5 z-50 bg-[#1E293B] text-white border border-[#38BDF8] px-4 py-2.5 rounded-lg shadow-xl flex items-center gap-2 text-sm font-medium animate-fade-in">
          <CheckCircle2 size={16} className="text-[#38BDF8]" />
          <span>{toastMessage}</span>
        </div>
      )}

      {/* Main Container */}
      <div className="w-full max-w-5xl flex flex-col gap-4">
        
        {/* Top Control Bar */}
        <div className="w-full bg-[#121824]/90 backdrop-blur-md border border-white/10 rounded-xl p-4 flex flex-wrap items-center justify-between gap-4 shadow-xl">
          {/* Sync Status Badge */}
          <div className="flex items-center gap-3">
            <div className="flex items-center gap-2 bg-[#0284C7]/15 border border-[#38BDF8]/30 px-3 py-1.5 rounded-full text-[#38BDF8] text-xs font-semibold">
              <Clock size={14} className="animate-spin-slow" />
              <span>Tự động đồng bộ: 1 tiếng / lần</span>
            </div>
            <div className="text-xs text-slate-400 font-mono">
              Lần tới sau: <span className="text-[#F59E0B] font-bold">{formatCountdown(nextSyncSeconds)}</span>
            </div>
          </div>

          {/* Action Buttons */}
          <div className="flex items-center gap-2.5 flex-wrap">
            {/* Manual Sync Button */}
            <button
              onClick={() => fetchData(true)}
              disabled={loading}
              className="flex items-center gap-1.5 px-3.5 py-1.5 rounded-lg text-xs font-bold bg-[#1E293B] hover:bg-[#334155] border border-white/15 text-slate-200 transition-all cursor-pointer shadow-sm disabled:opacity-50"
            >
              <RefreshCw size={13} className={loading ? 'animate-spin' : ''} />
              <span>{loading ? 'Đang tải...' : 'Làm mới'}</span>
            </button>

            {/* Snapshot Button */}
            <button
              onClick={handleCaptureSnapshot}
              className="flex items-center gap-1.5 px-3.5 py-1.5 rounded-lg text-xs font-bold bg-[#0284C7] hover:bg-[#0369A1] text-white transition-all cursor-pointer shadow-[0_0_12px_rgba(2,132,199,0.35)]"
            >
              <Camera size={13} />
              <span>Chụp ảnh Snapshot</span>
            </button>

            {/* Export Excel Button */}
            <button
              onClick={handleExportExcel}
              className="flex items-center gap-1.5 px-3.5 py-1.5 rounded-lg text-xs font-bold bg-[#16A34A] hover:bg-[#15803D] text-white transition-all cursor-pointer shadow-[0_0_12px_rgba(22,163,74,0.35)]"
            >
              <FileSpreadsheet size={13} />
              <span>Xuất Excel</span>
            </button>
          </div>
        </div>

        {/* ========================================================================= */}
        {/* KHU VỰC CHỤP ẢNH SNAPSHOT (CHÍNH XÁC 100% STYLE REPORT OPERATIONS DAY SHIFT) */}
        {/* ========================================================================= */}
        <div
          ref={captureAreaRef}
          id="inbReceivingCaptureArea"
          style={{
            background: '#FFFFFF',
            border: '1px solid #E2E8F0',
            borderRadius: '12px',
            padding: '24px 26px',
            boxShadow: '0 10px 25px -5px rgba(0, 0, 0, 0.25)',
            fontFamily: "'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif"
          }}
        >
          {/* HEADER BÁO CÁO TRONG ẢNH SNAPSHOT */}
          <div
            style={{
              display: 'flex',
              justifyContent: 'space-between',
              alignItems: 'center',
              marginBottom: '16px',
              paddingBottom: '12px',
              borderBottom: '1px solid #F1F5F9'
            }}
          >
            {/* BÊN TRÁI: GIỜ UPDATE dd/mm/yyyy hh:mm:ss */}
            <div style={{ flex: 1, display: 'flex', flexDirection: 'column', gap: '2px' }}>
              <span style={{ fontSize: '11.5px', color: '#64748B', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.5px' }}>
                Cập Nhật / 更新时间:
              </span>
              <span
                id="fcInbUpdateTime"
                style={{ fontFamily: "'JetBrains Mono', monospace", fontSize: '13.5px', fontWeight: 800, color: '#0F172A' }}
              >
                {data.updated_at || '--/--/---- --:--:--'}
              </span>
            </div>

            {/* CHÍNH GIỮA: TIÊU ĐỀ BẢNG CĂN GIỮA (TIẾNG TRUNG TO VÀ MÀU ĐEN) */}
            <div style={{ flex: 2, textAlign: 'center' }}>
              <div style={{ fontSize: '20px', fontWeight: 900, color: '#0F172A', letterSpacing: '0.5px' }}>
                THỐNG KÊ LƯỢNG ĐƠN NHẬN TRONG NGÀY
              </div>
              <div style={{ fontSize: '16px', fontWeight: 900, color: '#0F172A', marginTop: '3px', letterSpacing: '1px' }}>
                每日订单接收量统计报表
              </div>
            </div>

            {/* BÊN PHẢI: TRỐNG ĐỂ CĂN GIỮA TIÊU ĐỀ */}
            <div style={{ flex: 1 }}></div>
          </div>

          {/* TABLE WRAPPER */}
          <div style={{ background: '#FFFFFF', border: '1px solid #CBD5E1', borderRadius: '10px', overflowX: 'auto' }}>
            <table style={{ width: '100%', borderCollapse: 'collapse', background: '#FFFFFF' }}>
              <thead>
                <tr style={{ background: '#0B132B', color: '#FFFFFF', borderBottom: '2px solid #334155' }}>
                  <th style={{ padding: '11px 12px', textAlign: 'center', width: '200px', fontWeight: 900, fontSize: '13.5px', background: '#0B132B', color: '#FFFFFF', borderRight: '1px solid #334155' }}>
                    <div>PHÂN KHỐI</div>
                    <div style={{ fontSize: '11.5px', color: '#94A3B8', fontWeight: 700, marginTop: '2px' }}>分块 (BLOCK)</div>
                  </th>
                  <th style={{ padding: '11px 14px', textAlign: 'center', width: '220px', fontWeight: 900, fontSize: '13.5px', background: '#0B132B', color: '#FFFFFF', borderRight: '1px solid #334155' }}>
                    <div>LOẠI TUYẾN</div>
                    <div style={{ fontSize: '11.5px', color: '#94A3B8', fontWeight: 700, marginTop: '2px' }}>线路类型 (ROUTE)</div>
                  </th>
                  <th style={{ padding: '11px 20px', textAlign: 'right', fontWeight: 900, fontSize: '13.5px', background: '#0B132B', color: '#FFFFFF', borderRight: '1px solid #334155' }}>
                    <div>SỐ LƯỢNG ĐƠN / KIỆN</div>
                    <div style={{ fontSize: '11.5px', color: '#38BDF8', fontWeight: 700, marginTop: '2px' }}>进港件数 (PCS)</div>
                  </th>
                  <th style={{ padding: '11px 20px', textAlign: 'right', fontWeight: 900, fontSize: '13.5px', background: '#0B132B', color: '#FFFFFF' }}>
                    <div>TRỌNG LƯỢNG (TẤN)</div>
                    <div style={{ fontSize: '11.5px', color: '#FF8A4C', fontWeight: 700, marginTop: '2px' }}>重量 (TONS)</div>
                  </th>
                </tr>
              </thead>
              <tbody>
                {/* DÒNG TỔNG CỘNG / 合计 CHUẨN ĐẸP REPORT OPERATIONS DAY SHIFT */}
                <tr style={{ background: '#FFF7ED', borderBottom: '2px solid #FED7AA' }}>
                  <td style={{ textAlign: 'center', padding: '10px 8px', color: '#C2410C', fontWeight: 900, fontSize: '14.5px', borderRight: '1px solid #FED7AA' }}>
                    Σ
                  </td>
                  <td style={{ padding: '10px 14px', fontWeight: 900, color: '#9A3412', fontSize: '14px', textAlign: 'center' }}>
                    <div>TỔNG CỘNG / 合计</div>
                  </td>
                  <td style={{ padding: '10px 20px', textAlign: 'right', color: '#15803D', fontWeight: 900, fontSize: '15.5px', fontFamily: "'JetBrains Mono', monospace" }}>
                    {(data.grand_total?.metric1 || 0).toLocaleString()}
                  </td>
                  <td style={{ padding: '10px 20px', textAlign: 'right', color: '#C2410C', fontWeight: 900, fontSize: '15.5px', fontFamily: "'JetBrains Mono', monospace" }}>
                    {Number(data.grand_total?.metric2 || 0).toFixed(2)}
                  </td>
                </tr>

                {/* BLOCK 1: PICKUP TO HUB */}
                <tr style={{ borderBottom: '1px solid #F1F5F9', background: '#FFFFFF' }}>
                  <td
                    rowSpan={4}
                    style={{
                      background: '#FFFFFF',
                      color: '#0F172A',
                      fontWeight: 900,
                      fontSize: '13.5px',
                      textAlign: 'center',
                      verticalAlign: 'middle',
                      borderRight: '1px solid #E2E8F0',
                      borderBottom: '2px solid #CBD5E1',
                      padding: '12px',
                      letterSpacing: '0.3px'
                    }}
                  >
                    <div>Pickup to HUB</div>
                    <div style={{ fontSize: '11.5px', fontWeight: 700, color: '#64748B', marginTop: '2px' }}>取件进港</div>
                  </td>
                  <td style={{ padding: '10px 16px', fontWeight: 800, color: '#0F172A', textAlign: 'center', fontSize: '13.5px' }}>
                    LH - CTO SC
                  </td>
                  <td style={{ padding: '10px 20px', textAlign: 'right', fontFamily: "'JetBrains Mono', monospace", fontWeight: 900, fontSize: '14.5px', color: '#15803D' }}>
                    {(b1Map['LH - CTO SC']?.metric1 || 0).toLocaleString()}
                  </td>
                  <td style={{ padding: '10px 20px', textAlign: 'right', fontFamily: "'JetBrains Mono', monospace", fontWeight: 800, fontSize: '14.5px', color: '#0F172A' }}>
                    {Number(b1Map['LH - CTO SC']?.metric2 || 0).toFixed(2)}
                  </td>
                </tr>
                <tr style={{ borderBottom: '1px solid #F1F5F9', background: '#FFFFFF' }}>
                  <td style={{ padding: '10px 16px', fontWeight: 800, color: '#0F172A', textAlign: 'center', fontSize: '13.5px' }}>
                    LH - BN HUB
                  </td>
                  <td style={{ padding: '10px 20px', textAlign: 'right', fontFamily: "'JetBrains Mono', monospace", fontWeight: 900, fontSize: '14.5px', color: '#15803D' }}>
                    {(b1Map['LH - BN HUB']?.metric1 || 0).toLocaleString()}
                  </td>
                  <td style={{ padding: '10px 20px', textAlign: 'right', fontFamily: "'JetBrains Mono', monospace", fontWeight: 800, fontSize: '14.5px', color: '#0F172A' }}>
                    {Number(b1Map['LH - BN HUB']?.metric2 || 0).toFixed(2)}
                  </td>
                </tr>
                <tr style={{ borderBottom: '1px solid #F1F5F9', background: '#FFFFFF' }}>
                  <td style={{ padding: '10px 16px', fontWeight: 800, color: '#0F172A', textAlign: 'center', fontSize: '13.5px' }}>
                    Shuttle - HCM
                  </td>
                  <td style={{ padding: '10px 20px', textAlign: 'right', fontFamily: "'JetBrains Mono', monospace", fontWeight: 900, fontSize: '14.5px', color: '#15803D' }}>
                    {(b1Map['Shuttle - HCM']?.metric1 || 0).toLocaleString()}
                  </td>
                  <td style={{ padding: '10px 20px', textAlign: 'right', fontFamily: "'JetBrains Mono', monospace", fontWeight: 800, fontSize: '14.5px', color: '#0F172A' }}>
                    {Number(b1Map['Shuttle - HCM']?.metric2 || 0).toFixed(2)}
                  </td>
                </tr>
                <tr style={{ borderBottom: '2px solid #CBD5E1', background: '#FFFFFF' }}>
                  <td style={{ padding: '10px 16px', fontWeight: 800, color: '#0F172A', textAlign: 'center', fontSize: '13.5px' }}>
                    Shuttle - SE
                  </td>
                  <td style={{ padding: '10px 20px', textAlign: 'right', fontFamily: "'JetBrains Mono', monospace", fontWeight: 900, fontSize: '14.5px', color: '#15803D' }}>
                    {(b1Map['Shuttle - SE']?.metric1 || 0).toLocaleString()}
                  </td>
                  <td style={{ padding: '10px 20px', textAlign: 'right', fontFamily: "'JetBrains Mono', monospace", fontWeight: 800, fontSize: '14.5px', color: '#0F172A' }}>
                    {Number(b1Map['Shuttle - SE']?.metric2 || 0).toFixed(2)}
                  </td>
                </tr>

                {/* BLOCK 2: LH BN TO HUB */}
                <tr style={{ borderBottom: '1px solid #F1F5F9', background: '#FFFFFF' }}>
                  <td
                    rowSpan={3}
                    style={{
                      background: '#FFFFFF',
                      color: '#0F172A',
                      fontWeight: 900,
                      fontSize: '13.5px',
                      textAlign: 'center',
                      verticalAlign: 'middle',
                      borderRight: '1px solid #E2E8F0',
                      borderBottom: '2px solid #CBD5E1',
                      padding: '12px',
                      letterSpacing: '0.3px'
                    }}
                  >
                    <div>LH BN to HUB</div>
                    <div style={{ fontSize: '11.5px', fontWeight: 700, color: '#64748B', marginTop: '2px' }}>北宁调拨进港</div>
                  </td>
                  <td style={{ padding: '10px 16px', fontWeight: 800, color: '#0F172A', textAlign: 'center', fontSize: '13.5px' }}>
                    Shuttle - HCM
                  </td>
                  <td style={{ padding: '10px 20px', textAlign: 'right', fontFamily: "'JetBrains Mono', monospace", fontWeight: 900, fontSize: '14.5px', color: '#15803D' }}>
                    {(b2Map['Shuttle - HCM']?.metric1 || 0).toLocaleString()}
                  </td>
                  <td style={{ padding: '10px 20px', textAlign: 'right', fontFamily: "'JetBrains Mono', monospace", fontWeight: 800, fontSize: '14.5px', color: '#0F172A' }}>
                    {Number(b2Map['Shuttle - HCM']?.metric2 || 0).toFixed(2)}
                  </td>
                </tr>
                <tr style={{ borderBottom: '1px solid #F1F5F9', background: '#FFFFFF' }}>
                  <td style={{ padding: '10px 16px', fontWeight: 800, color: '#0F172A', textAlign: 'center', fontSize: '13.5px' }}>
                    Shuttle - SE
                  </td>
                  <td style={{ padding: '10px 20px', textAlign: 'right', fontFamily: "'JetBrains Mono', monospace", fontWeight: 900, fontSize: '14.5px', color: '#15803D' }}>
                    {(b2Map['Shuttle - SE']?.metric1 || 0).toLocaleString()}
                  </td>
                  <td style={{ padding: '10px 20px', textAlign: 'right', fontFamily: "'JetBrains Mono', monospace", fontWeight: 800, fontSize: '14.5px', color: '#0F172A' }}>
                    {Number(b2Map['Shuttle - SE']?.metric2 || 0).toFixed(2)}
                  </td>
                </tr>
                <tr style={{ borderBottom: '2px solid #CBD5E1', background: '#FFFFFF' }}>
                  <td style={{ padding: '10px 16px', fontWeight: 800, color: '#0F172A', textAlign: 'center', fontSize: '13.5px' }}>
                    LH - DC DĨ AN
                  </td>
                  <td style={{ padding: '10px 20px', textAlign: 'right', fontFamily: "'JetBrains Mono', monospace", fontWeight: 900, fontSize: '14.5px', color: '#15803D' }}>
                    {(b2Map['LH - DC DĨ AN']?.metric1 || 0).toLocaleString()}
                  </td>
                  <td style={{ padding: '10px 20px', textAlign: 'right', fontFamily: "'JetBrains Mono', monospace", fontWeight: 800, fontSize: '14.5px', color: '#0F172A' }}>
                    {Number(b2Map['LH - DC DĨ AN']?.metric2 || 0).toFixed(2)}
                  </td>
                </tr>

                {/* BLOCK 3: TOTAL */}
                <tr style={{ borderBottom: '1px solid #F1F5F9', background: '#FFFFFF' }}>
                  <td
                    rowSpan={5}
                    style={{
                      background: '#FFFFFF',
                      color: '#0F172A',
                      fontWeight: 900,
                      fontSize: '13.5px',
                      textAlign: 'center',
                      verticalAlign: 'middle',
                      borderRight: '1px solid #E2E8F0',
                      padding: '12px',
                      letterSpacing: '0.3px'
                    }}
                  >
                    <div>Total</div>
                    <div style={{ fontSize: '11.5px', fontWeight: 700, color: '#64748B', marginTop: '2px' }}>线路汇总</div>
                  </td>
                  <td style={{ padding: '10px 16px', fontWeight: 800, color: '#0F172A', textAlign: 'center', fontSize: '13.5px' }}>
                    LH - CTO SC
                  </td>
                  <td style={{ padding: '10px 20px', textAlign: 'right', fontFamily: "'JetBrains Mono', monospace", fontWeight: 900, fontSize: '14.5px', color: '#15803D' }}>
                    {(b3Map['LH - CTO SC']?.metric1 || 0).toLocaleString()}
                  </td>
                  <td style={{ padding: '10px 20px', textAlign: 'right', fontFamily: "'JetBrains Mono', monospace", fontWeight: 800, fontSize: '14.5px', color: '#0F172A' }}>
                    {Number(b3Map['LH - CTO SC']?.metric2 || 0).toFixed(2)}
                  </td>
                </tr>
                <tr style={{ borderBottom: '1px solid #F1F5F9', background: '#FFFFFF' }}>
                  <td style={{ padding: '10px 16px', fontWeight: 800, color: '#0F172A', textAlign: 'center', fontSize: '13.5px' }}>
                    LH - BN HUB
                  </td>
                  <td style={{ padding: '10px 20px', textAlign: 'right', fontFamily: "'JetBrains Mono', monospace", fontWeight: 900, fontSize: '14.5px', color: '#15803D' }}>
                    {(b3Map['LH - BN HUB']?.metric1 || 0).toLocaleString()}
                  </td>
                  <td style={{ padding: '10px 20px', textAlign: 'right', fontFamily: "'JetBrains Mono', monospace", fontWeight: 800, fontSize: '14.5px', color: '#0F172A' }}>
                    {Number(b3Map['LH - BN HUB']?.metric2 || 0).toFixed(2)}
                  </td>
                </tr>
                <tr style={{ borderBottom: '1px solid #F1F5F9', background: '#FFFFFF' }}>
                  <td style={{ padding: '10px 16px', fontWeight: 800, color: '#0F172A', textAlign: 'center', fontSize: '13.5px' }}>
                    Shuttle - HCM
                  </td>
                  <td style={{ padding: '10px 20px', textAlign: 'right', fontFamily: "'JetBrains Mono', monospace", fontWeight: 900, fontSize: '14.5px', color: '#15803D' }}>
                    {(b3Map['Shuttle - HCM']?.metric1 || 0).toLocaleString()}
                  </td>
                  <td style={{ padding: '10px 20px', textAlign: 'right', fontFamily: "'JetBrains Mono', monospace", fontWeight: 800, fontSize: '14.5px', color: '#0F172A' }}>
                    {Number(b3Map['Shuttle - HCM']?.metric2 || 0).toFixed(2)}
                  </td>
                </tr>
                <tr style={{ borderBottom: '1px solid #F1F5F9', background: '#FFFFFF' }}>
                  <td style={{ padding: '10px 16px', fontWeight: 800, color: '#0F172A', textAlign: 'center', fontSize: '13.5px' }}>
                    Shuttle - SE
                  </td>
                  <td style={{ padding: '10px 20px', textAlign: 'right', fontFamily: "'JetBrains Mono', monospace", fontWeight: 900, fontSize: '14.5px', color: '#15803D' }}>
                    {(b3Map['Shuttle - SE']?.metric1 || 0).toLocaleString()}
                  </td>
                  <td style={{ padding: '10px 20px', textAlign: 'right', fontFamily: "'JetBrains Mono', monospace", fontWeight: 800, fontSize: '14.5px', color: '#0F172A' }}>
                    {Number(b3Map['Shuttle - SE']?.metric2 || 0).toFixed(2)}
                  </td>
                </tr>
                <tr style={{ borderBottom: '1px solid #CBD5E1', background: '#FFFFFF' }}>
                  <td style={{ padding: '10px 16px', fontWeight: 800, color: '#0F172A', textAlign: 'center', fontSize: '13.5px' }}>
                    LH - DC DĨ AN
                  </td>
                  <td style={{ padding: '10px 20px', textAlign: 'right', fontFamily: "'JetBrains Mono', monospace", fontWeight: 900, fontSize: '14.5px', color: '#15803D' }}>
                    {(b3Map['LH - DC DĨ AN']?.metric1 || 0).toLocaleString()}
                  </td>
                  <td style={{ padding: '10px 20px', textAlign: 'right', fontFamily: "'JetBrains Mono', monospace", fontWeight: 800, fontSize: '14.5px', color: '#0F172A' }}>
                    {Number(b3Map['LH - DC DĨ AN']?.metric2 || 0).toFixed(2)}
                  </td>
                </tr>
              </tbody>
            </table>
          </div>
        </div>

      </div>
    </div>
  );
};

export default InboundReceivingReport;
