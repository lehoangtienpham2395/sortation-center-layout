import sys

sys.stdout.reconfigure(encoding='utf-8')

print("🚀 Restoring exact original font, colors (#092518), and styling of 'Xuất Báo Cáo' button on the top right...")

for fn in ['src/components/InboundDashboard.tsx', 'src/components/InboundDashboardV2.tsx']:
    with open(fn, 'r', encoding='utf-8') as f:
        c = f.read()

    # Current compact button on top right
    old_btn = '''            <button
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
            </button>'''

    # Restored original button style (class google-sync-btn, background #092518, exact font and green excel icon text-[#10b981]) but compact size
    new_btn = '''            <button
              className="google-sync-btn"
              onClick={handleExportCSV}
              style={{
                width: 'auto',
                padding: '5px 14px',
                fontSize: '12px',
                background: '#092518',
                border: '1px solid rgba(16, 185, 129, 0.4)',
                borderRadius: '20px',
                display: 'inline-flex',
                alignItems: 'center',
                gap: '6px'
              }}
              title="Xuất báo cáo Excel / CSV"
            >
              <i className="fa-solid fa-file-excel text-[#10b981]" style={{ fontSize: '13px' }}></i>
              Xuất Báo Cáo
            </button>'''

    if old_btn in c:
        c = c.replace(old_btn, new_btn)
        print(f"Restored exact original button style in {fn}!")
    else:
        print(f"WARNING: Could not find old_btn in {fn}")

    with open(fn, 'w', encoding='utf-8') as f:
        f.write(c)

print("✅ 'Xuất Báo Cáo' button restored to exact original font, class (google-sync-btn), and background color (#092518)!")
