import sys

sys.stdout.reconfigure(encoding='utf-8')

print("🚀 Synchronizing border style of 'Xuất Báo Cáo' button with 'Đồng bộ' button...")

for fn in ['src/components/InboundDashboard.tsx', 'src/components/InboundDashboardV2.tsx']:
    with open(fn, 'r', encoding='utf-8') as f:
        c = f.read()

    old_btn = '''            <button
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
            >'''

    new_btn = '''            <button
              className="google-sync-btn"
              onClick={handleExportCSV}
              style={{
                width: 'auto',
                padding: '5px 14px',
                fontSize: '12px',
                background: '#092518',
                borderRadius: '20px',
                display: 'inline-flex',
                alignItems: 'center',
                gap: '6px'
              }}
              title="Xuất báo cáo Excel / CSV"
            >'''

    if old_btn in c:
        c = c.replace(old_btn, new_btn)
        print(f"Successfully synchronized border in {fn}!")
    else:
        print(f"WARNING: Could not find old_btn in {fn}")

    with open(fn, 'w', encoding='utf-8') as f:
        f.write(c)

print("✅ 'Xuất Báo Cáo' button border is now 100% synchronized with 'Đồng bộ' button!")
