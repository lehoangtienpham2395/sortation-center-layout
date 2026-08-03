import sys

sys.stdout.reconfigure(encoding='utf-8')

print("🚀 Enhancing Forecast Card Label Size and Font Weight...")

for fn in ['src/components/InboundDashboard.tsx', 'src/components/InboundDashboardV2.tsx']:
    with open(fn, 'r', encoding='utf-8') as f:
        c = f.read()

    old_html = '''        {/* KPI 4: Forecast */}
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

    new_html = '''        {/* KPI 4: Forecast */}
        <div className="kpi-card accent-orange glass-card report-glow-card glow-purple">
          <div className="kpi-card-header">
            <span className="kpi-title" style={{ fontSize: '1.08rem', fontWeight: 700, letterSpacing: '0.02em' }}>Forecast</span>
            <i className="fa-solid fa-chart-line kpi-icon"></i>
          </div>
          <div className="kpi-card-body" style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
            <div style={{ display: 'flex', alignItems: 'baseline', gap: '10px' }}>
              <span className="kpi-value"><NumberTicker value={totalForecast} /></span>
              <span style={{ fontSize: '1.08rem', color: '#E2E8F0', fontWeight: 700, letterSpacing: '0.01em' }}>(~{totalForecastWeight.toFixed(1).replace('.', ',')} Tấn)</span>
            </div>
            <div style={{ display: 'flex', flexDirection: 'column', gap: '4px', fontSize: '0.98rem', color: '#E2E8F0', borderTop: '1px solid rgba(255,255,255,0.08)', paddingTop: '6px', marginTop: '4px' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                <span style={{ fontWeight: 700, color: '#F1F5F9', fontSize: '0.98rem' }}>Shuttle:</span>
                <strong style={{ color: '#a3e635', fontSize: '1.18rem', fontWeight: 800 }}>
                  <NumberTicker value={finalShuttleForecast} /> <span style={{ fontSize: '0.9rem', color: '#CBD5E1', fontWeight: 600 }}>({finalShuttleWeight.toFixed(1).replace('.', ',')} Tấn)</span>
                </strong>
              </div>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                <span style={{ fontWeight: 700, color: '#F1F5F9', fontSize: '0.98rem' }}>Linehaul:</span>
                <strong style={{ color: '#f97316', fontSize: '1.18rem', fontWeight: 800 }}>
                  <NumberTicker value={finalLinehaulForecast} /> <span style={{ fontSize: '0.9rem', color: '#CBD5E1', fontWeight: 600 }}>({finalLinehaulWeight.toFixed(1).replace('.', ',')} Tấn)</span>
                </strong>
              </div>
            </div>
          </div>
          <div className="kpi-glow"></div>
        </div>'''

    if old_html in c:
        c = c.replace(old_html, new_html)
        print(f"Updated font size and weight in {fn}!")
    else:
        print(f"WARNING: Could not find old_html in {fn}")

    with open(fn, 'w', encoding='utf-8') as f:
        f.write(c)

print("✅ Forecast Card labels are now larger and bolder!")
