import sys

sys.stdout.reconfigure(encoding='utf-8')

print("🚀 Fixing TypeScript comment syntax in React components...")

for fn in ['src/components/InboundDashboard.tsx', 'src/components/InboundDashboardV2.tsx']:
    with open(fn, 'r', encoding='utf-8') as f:
        c = f.read()

    # Clean JS comments
    c = c.replace(
        '# Sức chứa quy đổi chuẩn 1 xe xe tải chạy tuyến:\n      # - Linehaul BN HUB: ~1,400 đơn/chuyến (ví dụ: 2,115 đơn = đúng 2 xe chuẩn)\n      # - Shuttle Bưu cục (DT Sa Đéc, SG Củ Chi...): ~450 - 500 đơn/chuyến (ví dụ: DT Sa Đéc 1,096 đơn = đúng 2 xe chuẩn)',
        '// Sức chứa quy đổi chuẩn 1 xe xe tải chạy tuyến:\n      // - Linehaul BN HUB: ~1,400 đơn/chuyến (ví dụ: 2,115 đơn = đúng 2 xe chuẩn)\n      // - Shuttle Bưu cục (DT Sa Đéc, SG Củ Chi...): ~450 - 500 đơn/chuyến (ví dụ: DT Sa Đéc 1,096 đơn = đúng 2 xe chuẩn)'
    )

    with open(fn, 'w', encoding='utf-8') as f:
        f.write(c)

print("✅ TypeScript comment syntax fixed!")
