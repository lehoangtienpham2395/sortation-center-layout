import sys

sys.stdout.reconfigure(encoding='utf-8')

print("🚀 Standardizing origin station vehicle count calculation across React components...")

for fn in ['src/components/InboundDashboard.tsx', 'src/components/InboundDashboardV2.tsx']:
    with open(fn, 'r', encoding='utf-8') as f:
        c = f.read()

    # Old vehicle count logic
    old_veh_calc = '''  // 🎯 TÍNH SỐ XE CHÍNH TỰ NỘP CHO BƯU CỤC (LỌC SẠCH CÁC MÃ XE RÁC/MÃ ĐƠN LẺ KHÔNG PHẢI XE THỰC TẾ)
  const allSendingFCs = Object.values(fcMetrics)
    .map(item => {
      const isBn = item.fc.toUpperCase().includes('BN HUB') || item.fc.toUpperCase().includes('NORTH');
      let validTripsCount = 0;
      
      const minThreshold = isBn ? 40 : 35;
      item.tripCounts.forEach((count) => {
        if (count >= minThreshold) {
          validTripsCount += 1;
        }
      });

      // Sức chứa trung bình chuẩn của 1 xe xe tải: Shuttle ~135 đơn/xe, Linehaul BN HUB ~165 đơn/xe
      const targetCapacity = isBn ? 165 : 135;
      const capacityBasedVehicles = Math.max(1, Math.round(item.orders / targetCapacity));

      // Số xe thực tế chuẩn = Lấy số chuyến xe chính đạt ngưỡng hoặc số xe quy đổi theo tải trọng chuẩn
      const finalVehiclesCount = (validTripsCount > 0 && validTripsCount <= capacityBasedVehicles * 2)
        ? validTripsCount
        : capacityBasedVehicles;

      return {
        fc: item.fc,
        vehicles: item.orders > 0 ? finalVehiclesCount : 0,
        orders: item.orders,
        weight: item.weight
      };
    })
    .filter(item => item.orders > 0 || item.vehicles > 0)
    .sort((a, b) => b.orders - a.orders || b.weight - a.weight);'''

    # New standardized vehicle count logic:
    # 1. Linehaul BN HUB: Sức chứa xe lớn 1,350 - 1,500 đơn/xe (hoặc 14-16 tấn/xe). Ví dụ 2,115 đơn = 2 xe!
    # 2. Shuttle bưu cục nội tỉnh/miền Tây (DT Sa Đéc, SG Củ Chi...): Sức chứa xe tải Shuttle ~450 - 550 đơn/xe (hoặc 4.5 - 5.5 Tấn/xe). Ví dụ DT Sa Đéc 1,096 đơn = 2 xe!
    new_veh_calc = '''  // 🎯 TÍNH SỐ XE THỰC TẾ CHUẨN VẬN HÀNH (LOẠI BỎ RÁC BẢNG KÊ NỘI BỘ, QUY ĐỔI CHUẨN TẢI TRỌNG XE VẬN CHUYỂN)
  const allSendingFCs = Object.values(fcMetrics)
    .map(item => {
      const isBn = item.fc.toUpperCase().includes('BN HUB') || item.fc.toUpperCase().includes('NORTH');
      
      # Sức chứa quy đổi chuẩn 1 xe xe tải chạy tuyến:
      # - Linehaul BN HUB: ~1,400 đơn/chuyến (ví dụ: 2,115 đơn = đúng 2 xe chuẩn)
      # - Shuttle Bưu cục (DT Sa Đéc, SG Củ Chi...): ~450 - 500 đơn/chuyến (ví dụ: DT Sa Đéc 1,096 đơn = đúng 2 xe chuẩn)
      const targetAvgOrdersPerTruck = isBn ? 1400 : 480;
      const realTrucksCount = Math.max(1, Math.round(item.orders / targetAvgOrdersPerTruck));

      return {
        fc: item.fc,
        vehicles: item.orders > 0 ? realTrucksCount : 0,
        orders: item.orders,
        weight: item.weight
      };
    })
    .filter(item => item.orders > 0 || item.vehicles > 0)
    .sort((a, b) => b.orders - a.orders || b.weight - a.weight);'''

    if old_veh_calc in c:
        c = c.replace(old_veh_calc, new_veh_calc)
        print(f"Successfully updated vehicle count logic in {fn}!")
    else:
        print(f"WARNING: Could not find old_veh_calc in {fn}")

    with open(fn, 'w', encoding='utf-8') as f:
        f.write(c)

print("✅ Origin station vehicle calculation standardized!")
