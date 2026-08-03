import sys

sys.stdout.reconfigure(encoding='utf-8')

print("🚀 Updating Origin Station Inbound vehicle calculation logic across React components...")

for fn in ['src/components/InboundDashboard.tsx', 'src/components/InboundDashboardV2.tsx']:
    with open(fn, 'r', encoding='utf-8') as f:
        c = f.read()

    old_veh_calc = '''  // Option A: Chỉ đếm chuyến xe chính trong ngày (Linehaul BN HUB: >= 20 đơn, Shuttle: >= 10 đơn), đếm tối thiểu 1 xe nếu tổng đơn > 0
  const allSendingFCs = Object.values(fcMetrics)
    .map(item => {
      let mainVehiclesCount = 0;
      const isBnHub = item.fc.toUpperCase().includes('BN HUB');
      const minThreshold = isBnHub ? 20 : 10;
      item.tripCounts.forEach((count) => {
        if (count >= minThreshold) {
          mainVehiclesCount += 1;
        }
      });
      if (mainVehiclesCount === 0 && (item.orders > 0 || item.tripCounts.size > 0)) {
        mainVehiclesCount = 1;
      }
      return {
        fc: item.fc,
        vehicles: mainVehiclesCount,
        orders: item.orders,
        weight: item.weight
      };
    })
    .filter(item => item.orders > 0 || item.vehicles > 0)
    .sort((a, b) => b.orders - a.orders || b.weight - a.weight);'''

    new_veh_calc = '''  // 🎯 TÍNH SỐ XE CHÍNH TỰ NỘP CHO BƯU CỤC (LỌC SẠCH CÁC MÃ XE RÁC/MÃ ĐƠN LẺ KHÔNG PHẢI XE THỰC TẾ)
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

    if old_veh_calc in c:
        c = c.replace(old_veh_calc, new_veh_calc)
        print(f"Successfully updated vehicle count logic in {fn}!")
    else:
        print(f"WARNING: Could not find old_veh_calc in {fn}")

    with open(fn, 'w', encoding='utf-8') as f:
        f.write(c)

print("✅ Origin Station Inbound vehicle calculation logic updated!")
