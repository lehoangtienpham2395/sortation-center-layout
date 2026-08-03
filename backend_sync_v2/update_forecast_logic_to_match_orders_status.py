import re
import glob
import os
import sys

sys.stdout.reconfigure(encoding='utf-8')

print("🚀 Updating Forecast KPI Card logic to 100% DERIVE FROM Orders Status waterfall logic...")

for fn in ['src/components/InboundDashboard.tsx', 'src/components/InboundDashboardV2.tsx']:
    with open(fn, 'r', encoding='utf-8') as f:
        c = f.read()

    # 1. Update the loop inside isOpMatch to calculate forecastShuttle and forecastLinehaul directly from un-inbounded waterfall stages
    old_loop_block = '''      // 🎯 DỰ BÁO ĐƠN RỚT (DISPATCH SOURCE): Chưa Inbound và chưa Outbound
      const hasInboundScan = Boolean(
        d['inbound_scandate'] || d['Inbound Time'] || d['inbound_time'] || d['Inbound_time'] || d['inbound_date'] || d['Ngày nhập kho'] || d['Ngay nhap kho']
      );
      const hasOutboundScan = Boolean(
        d['outbound_scandate'] || d['Outbound Time'] || d['outbound_time'] || d['Outbound_time'] || d['outbound_date'] || d['Ngày xuất kho'] || d['Ngay xuat kho']
      );
      const isDoneStatus = ['Inbound', 'Outbound', 'Canceled', 'Đã nhập kho', 'Đã xuất kho', 'Đã hủy'].includes(status);

      if (!isDoneStatus && !hasInboundScan && !hasOutboundScan) {
        if (isNorth) {
          forecastLinehaul += vol;
        } else {
          forecastShuttle += vol;
        }
        isForecastMember = true;
      }

      const arrOpDate = normalizeDateStr(d['op_date_arrival'] || d['Ngày vận hành_Arrival'] || d['Ngy vn hnh_Arrival'] || (d['Arrival Time'] ? getOperatingDateFromTimestamp(d['Arrival Time']) : ''));
      const pkOpDate  = normalizeDateStr(d['op_date_pickup']  || d['Ngày vận hành_Pickup']  || d['Ngy vn hnh_Pickup']  || '');
      const inbOpDate = normalizeDateStr(d['op_date_inbound'] || d['Ngày vận hành_Inbound'] || d['Ngy vn hnh_Inbound'] || '');

      const isOpMatch = isForecastMember || (normFcDate === normActiveDate) || (arrOpDate === normActiveDate) || (pkOpDate === normActiveDate) || (inbOpDate === normActiveDate);

      // 🎯 BIỂU ĐỒ ORDERS STATUS TÍNH TẤT CẢ CÁC ĐƠN THUỘC CA VẬN HÀNH HÔM NAY (BAO GỒM CẢ BN HUB / MIỀN BẮC)
      if (isOpMatch) {
        const wfStatus = getWaterfallStatus(d);
        if (stages[wfStatus]) {
          stages[wfStatus].orders += vol;
          stages[wfStatus].weight += wt;
          if (wt > 0) stagesWithWeight[wfStatus] += vol;
        }
        if (wfStatus === 'Transporting') {
          const pkSt = (d['pickup_station'] || d['station_name'] || '').trim().toUpperCase();
          if (pkSt && pkSt !== 'BN HUB') {
            stationTransportingMap[pkSt] = (stationTransportingMap[pkSt] || 0) + vol;
          }
        }
      }'''

    new_loop_block = '''      const arrOpDate = normalizeDateStr(d['op_date_arrival'] || d['Ngày vận hành_Arrival'] || d['Ngy vn hnh_Arrival'] || (d['Arrival Time'] ? getOperatingDateFromTimestamp(d['Arrival Time']) : ''));
      const pkOpDate  = normalizeDateStr(d['op_date_pickup']  || d['Ngày vận hành_Pickup']  || d['Ngy vn hnh_Pickup']  || '');
      const inbOpDate = normalizeDateStr(d['op_date_inbound'] || d['Ngày vận hành_Inbound'] || d['Ngy vn hnh_Inbound'] || '');

      const isOpMatch = (normFcDate === normActiveDate) || (arrOpDate === normActiveDate) || (pkOpDate === normActiveDate) || (inbOpDate === normActiveDate);

      // 🎯 BIỂU ĐỒ ORDERS STATUS TÍNH TẤT CẢ CÁC ĐƠN THUỘC CA VẬN HÀNH HÔM NAY
      if (isOpMatch) {
        const wfStatus = getWaterfallStatus(d);
        if (stages[wfStatus]) {
          stages[wfStatus].orders += vol;
          stages[wfStatus].weight += wt;
          if (wt > 0) stagesWithWeight[wfStatus] += vol;
        }

        // 🎯 TÍNH THẺ FORECAST TRỰC TIẾP TỪ LOGIC ORDERS STATUS (TẤT CẢ CÁC ĐƠN CHƯA INBOUND HÔM NAY)
        if (wfStatus !== 'Inbound') {
          if (isNorth) {
            forecastLinehaul += vol;
          } else {
            forecastShuttle += vol;
          }
        }

        if (wfStatus === 'Transporting') {
          const pkSt = (d['pickup_station'] || d['station_name'] || '').trim().toUpperCase();
          if (pkSt && pkSt !== 'BN HUB') {
            stationTransportingMap[pkSt] = (stationTransportingMap[pkSt] || 0) + vol;
          }
        }
      }'''

    if old_loop_block in c:
        c = c.replace(old_loop_block, new_loop_block)
        print(f"Replaced loop block in {fn}!")
    else:
        print(f"WARNING: Could not find old_loop_block in {fn}!")

    # 2. Update final variable assignments to use computed forecastShuttle & forecastLinehaul directly
    old_vars = '''  const finalShuttleForecast = isFutureDate ? 0 : (
    effectiveKpiSummary?.shuttle ?? forecastShuttle
  );

  const finalLinehaulForecast = isFutureDate ? 0 : (
    effectiveKpiSummary?.linehaul ?? forecastLinehaul
  );

  const totalForecast = isFutureDate ? 0 : (
    effectiveKpiSummary?.forecast_total ?? (finalShuttleForecast + finalLinehaulForecast)
  );'''

    new_vars = '''  const finalShuttleForecast = isFutureDate ? 0 : forecastShuttle;
  const finalLinehaulForecast = isFutureDate ? 0 : forecastLinehaul;
  const totalForecast = isFutureDate ? 0 : (finalShuttleForecast + finalLinehaulForecast);'''

    if old_vars in c:
        c = c.replace(old_vars, new_vars)
        print(f"Replaced final variables block in {fn}!")
    else:
        print(f"WARNING: Could not find old_vars in {fn}!")

    with open(fn, 'w', encoding='utf-8') as f:
        f.write(c)

print("✅ Updated Forecast logic in React components successfully!")
