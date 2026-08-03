import sys

sys.stdout.reconfigure(encoding='utf-8')

print("🚀 Moving 'Xuất báo cáo' button to the top-right corner and scaling it down by 40%...")

for fn in ['src/components/InboundDashboard.tsx', 'src/components/InboundDashboardV2.tsx']:
    with open(fn, 'r', encoding='utf-8') as f:
        c = f.read()

    # 1. Remove Xuất Báo Cáo from left side
    old_left = '''        {/* LEFT: Sync Button + Export Button + Logo */}
        <div style={{ display: 'flex', alignItems: 'center', gap: '14px', flexShrink: 0 }}>
          <button
            className="google-sync-btn"
            onClick={fetchAndUpdateData}
            disabled={loading}
            style={{ width: 'auto', padding: '10px 20px' }}
          >
            <span className="w-1.5 h-1.5 rounded-full bg-[#22c55e] animate-pulse shrink-0" style={{ marginRight: '8px' }} />
            {loading ? 'Đang đồng bộ...' : 'Đồng bộ'}
          </button>

          <button
            className="google-sync-btn"
            onClick={handleExportCSV}
            style={{ width: 'auto', padding: '10px 18px', background: '#092518' }}
          >
            <i className="fa-solid fa-file-excel text-[#10b981]" style={{ marginRight: '6px' }}></i>
            Xuất Báo Cáo
          </button>

          <img src="logo.png" alt="J&T Cargo Logo" className="jt-logo" style={{ height: '80px', borderRadius: '10px', display: 'block' }} />
        </div>'''

    new_left = '''        {/* LEFT: Sync Button + Logo */}
        <div style={{ display: 'flex', alignItems: 'center', gap: '14px', flexShrink: 0 }}>
          <button
            className="google-sync-btn"
            onClick={fetchAndUpdateData}
            disabled={loading}
            style={{ width: 'auto', padding: '10px 20px' }}
          >
            <span className="w-1.5 h-1.5 rounded-full bg-[#22c55e] animate-pulse shrink-0" style={{ marginRight: '8px' }} />
            {loading ? 'Đang đồng bộ...' : 'Đồng bộ'}
          </button>

          <img src="logo.png" alt="J&T Cargo Logo" className="jt-logo" style={{ height: '80px', borderRadius: '10px', display: 'block' }} />
        </div>'''

    if old_left in c:
        c = c.replace(old_left, new_left)

    # 2. Add compact 'Xuất báo cáo' button (40% smaller) to the top right section next to Update badge
    old_right = '''        {/* RIGHT: Status + Date Picker */}
        <div className="header-right" style={{ flexShrink: 0, display: 'flex', flexDirection: 'column', alignItems: 'flex-end', gap: '8px' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
            <div style={{ 
              fontSize: '11px', 
              color: '#B8F7E4', 
              background: 'rgba(184, 247, 228, 0.05)', 
              border: '1px solid rgba(184, 247, 228, 0.2)', 
              padding: '5px 12px', 
              borderRadius: '20px', 
              fontWeight: 600, 
              fontFamily: "'Inter', sans-serif",
              display: 'flex',
              alignItems: 'center',
              gap: '6px',
              textShadow: '0 0 8px rgba(184,247,228,0.3)'
            }}>
              <span className="w-1.5 h-1.5 rounded-full bg-[#B8F7E4] animate-pulse" />
              Update: {lastUpdate || lastUpdateObj?.last_update || 'Đang cập nhật...'}
            </div>
          </div>'''

    new_right = '''        {/* RIGHT: Status + Export Button + Date Picker */}
        <div className="header-right" style={{ flexShrink: 0, display: 'flex', flexDirection: 'column', alignItems: 'flex-end', gap: '8px' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
            <button
              className="btn-glow"
              onClick={handleExportCSV}
              style={{
                height: '26px',
                padding: '3px 12px',
                fontSize: '11px',
                fontWeight: 600,
                background: 'rgba(16, 185, 129, 0.15)',
                border: '1px solid rgba(16, 185, 129, 0.4)',
                color: '#10b981',
                borderRadius: '14px',
                cursor: 'pointer',
                display: 'inline-flex',
                alignItems: 'center',
                gap: '5px',
                whiteSpace: 'nowrap',
                transition: 'all 0.2s ease-in-out'
              }}
              title="Xuất báo cáo Excel / CSV"
            >
              <i className="fa-solid fa-file-excel" style={{ fontSize: '11px' }}></i>
              Xuất báo cáo
            </button>
            <div style={{ 
              fontSize: '11px', 
              color: '#B8F7E4', 
              background: 'rgba(184, 247, 228, 0.05)', 
              border: '1px solid rgba(184, 247, 228, 0.2)', 
              padding: '4px 12px', 
              borderRadius: '20px', 
              fontWeight: 600, 
              fontFamily: "'Inter', sans-serif",
              display: 'flex',
              alignItems: 'center',
              gap: '6px',
              textShadow: '0 0 8px rgba(184,247,228,0.3)'
            }}>
              <span className="w-1.5 h-1.5 rounded-full bg-[#B8F7E4] animate-pulse" />
              Update: {lastUpdate || lastUpdateObj?.last_update || 'Đang cập nhật...'}
            </div>
          </div>'''

    if old_right in c:
        c = c.replace(old_right, new_right)
        print(f"Successfully moved button to top-right in {fn}!")
    else:
        print(f"WARNING: Could not find old_right in {fn}")

    with open(fn, 'w', encoding='utf-8') as f:
        f.write(c)

print("✅ 'Xuất báo cáo' button moved to top-right corner and scaled down by 40%!")
