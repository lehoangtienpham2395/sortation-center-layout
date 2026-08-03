import re
import json
import glob
import os
import sys

sys.stdout.reconfigure(encoding='utf-8')

print("🚀 Deploying Option 1 (Horizontal Layout) Forecast Weight Feature...")

# 1. Update InboundDashboard.tsx and InboundDashboardV2.tsx
for fn in ['src/components/InboundDashboard.tsx', 'src/components/InboundDashboardV2.tsx']:
    with open(fn, 'r', encoding='utf-8') as f:
        c = f.read()

    # 1.1 Declare weight variables
    c = c.replace(
        'let forecastShuttle = 0;\n  let forecastLinehaul = 0;',
        'let forecastShuttle = 0;\n  let forecastLinehaul = 0;\n  let forecastShuttleWeight = 0;\n  let forecastLinehaulWeight = 0;'
    )

    # 1.2 Accumulate weight in loop
    old_acc = '''        // 🎯 TÍNH THẺ FORECAST TRỰC TIẾP TỪ LOGIC ORDERS STATUS (TẤT CẢ CÁC ĐƠN CHƯA INBOUND HÔM NAY)
        if (wfStatus !== 'Inbound') {
          if (isNorth) {
            forecastLinehaul += vol;
          } else {
            forecastShuttle += vol;
          }
        }'''

    new_acc = '''        // 🎯 TÍNH THẺ FORECAST TRỰC TIẾP TỪ LOGIC ORDERS STATUS (TẤT CẢ CÁC ĐƠN CHƯA INBOUND HÔM NAY)
        if (wfStatus !== 'Inbound') {
          if (isNorth) {
            forecastLinehaul += vol;
            forecastLinehaulWeight += wt;
          } else {
            forecastShuttle += vol;
            forecastShuttleWeight += wt;
          }
        }'''

    if old_acc in c:
        c = c.replace(old_acc, new_acc)

    # 1.3 Assign final weight variables
    old_vars = '''  const finalShuttleForecast = isFutureDate ? 0 : forecastShuttle;
  const finalLinehaulForecast = isFutureDate ? 0 : forecastLinehaul;
  const totalForecast = isFutureDate ? 0 : (finalShuttleForecast + finalLinehaulForecast);'''

    new_vars = '''  const finalShuttleForecast = isFutureDate ? 0 : forecastShuttle;
  const finalLinehaulForecast = isFutureDate ? 0 : forecastLinehaul;
  const totalForecast = isFutureDate ? 0 : (finalShuttleForecast + finalLinehaulForecast);

  const finalShuttleWeight = isFutureDate ? 0 : (effectiveKpiSummary?.shuttle_weight ?? forecastShuttleWeight);
  const finalLinehaulWeight = isFutureDate ? 0 : (effectiveKpiSummary?.linehaul_weight ?? forecastLinehaulWeight);
  const totalForecastWeight = isFutureDate ? 0 : (effectiveKpiSummary?.forecast_weight_ton ?? (finalShuttleWeight + finalLinehaulWeight));'''

    if old_vars in c:
        c = c.replace(old_vars, new_vars)

    # 1.4 Update HTML for Card 4 (Option 1 Horizontal Layout)
    old_html = '''        {/* KPI 4: Forecast */}
        <div className="kpi-card accent-orange glass-card report-glow-card glow-purple">
          <div className="kpi-card-header">
            <span className="kpi-title">Forecast</span>
            <i className="fa-solid fa-chart-line kpi-icon"></i>
          </div>
          <div className="kpi-card-body" style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
            <span className="kpi-value"><NumberTicker value={totalForecast} /></span>
            <div style={{ display: 'flex', flexDirection: 'column', gap: '3px', fontSize: '0.88rem', color: 'var(--text-secondary)', borderTop: '1px solid rgba(255,255,255,0.06)', paddingTop: '5px', marginTop: '4px' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                <span>Shuttle:</span>
                <strong style={{ color: '#a3e635', fontSize: '1.05rem' }}><NumberTicker value={finalShuttleForecast} /></strong>
              </div>
              <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                <span>Linehaul:</span>
                <strong style={{ color: '#f97316', fontSize: '1.05rem' }}><NumberTicker value={finalLinehaulForecast} /></strong>
              </div>
            </div>
          </div>
          <div className="kpi-glow"></div>
        </div>'''

    new_html = '''        {/* KPI 4: Forecast */}
        <div className="kpi-card accent-orange glass-card report-glow-card glow-purple">
          <div className="kpi-card-header">
            <span className="kpi-title">Forecast</span>
            <i className="fa-solid fa-chart-line kpi-icon"></i>
          </div>
          <div className="kpi-card-body" style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
            <div style={{ display: 'flex', alignItems: 'baseline', gap: '8px' }}>
              <span className="kpi-value"><NumberTicker value={totalForecast} /></span>
              <span style={{ fontSize: '0.9rem', color: '#94A3B8', fontWeight: 500 }}>(~{totalForecastWeight.toFixed(1).replace('.', ',')} Tấn)</span>
            </div>
            <div style={{ display: 'flex', flexDirection: 'column', gap: '3px', fontSize: '0.88rem', color: 'var(--text-secondary)', borderTop: '1px solid rgba(255,255,255,0.06)', paddingTop: '5px', marginTop: '4px' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                <span>Shuttle:</span>
                <strong style={{ color: '#a3e635', fontSize: '1.05rem' }}>
                  <NumberTicker value={finalShuttleForecast} /> <span style={{ fontSize: '0.8rem', color: '#94A3B8', fontWeight: 400 }}>({finalShuttleWeight.toFixed(1).replace('.', ',')} Tấn)</span>
                </strong>
              </div>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                <span>Linehaul:</span>
                <strong style={{ color: '#f97316', fontSize: '1.05rem' }}>
                  <NumberTicker value={finalLinehaulForecast} /> <span style={{ fontSize: '0.8rem', color: '#94A3B8', fontWeight: 400 }}>({finalLinehaulWeight.toFixed(1).replace('.', ',')} Tấn)</span>
                </strong>
              </div>
            </div>
          </div>
          <div className="kpi-glow"></div>
        </div>'''

    if old_html in c:
        c = c.replace(old_html, new_html)
        print(f"Replaced HTML in {fn} successfully!")
    else:
        print(f"WARNING: Could not find old_html in {fn}")

    with open(fn, 'w', encoding='utf-8') as f:
        f.write(c)

print("✅ React components updated with Option 1 Forecast Weight Layout!")
