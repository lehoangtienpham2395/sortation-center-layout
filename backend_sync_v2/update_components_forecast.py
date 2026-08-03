import os
import re
import sys

sys.stdout.reconfigure(encoding='utf-8')

for fn in ['src/components/InboundDashboard.tsx', 'src/components/InboundDashboardV2.tsx']:
    with open(fn, 'r', encoding='utf-8') as f:
        c = f.read()

    # 1. Add forecastOrdersNow and forecastOrdersLive accumulation
    c = c.replace(
        'let forecastShuttle = 0;\n  let forecastLinehaul = 0;',
        'let forecastOrdersNow = 0;\n  let forecastOrdersLive = 0;'
    )

    c = c.replace(
        '''      if (!isInbound && status !== 'Outbound') {
        if (isNorth) {
          forecastLinehaul += vol;
        } else {
          forecastShuttle += vol;
        }
        isForecastMember = true;
      }''',
        '''      if (!isInbound && status !== 'Outbound' && !d['Inbound Time'] && !d['inbound_time'] && !d['Outbound Time'] && !d['outbound_time']) {
        const normCreatedDate = normalizeDateStr(d['op_date_created'] || d['Ngày vận hành_Created'] || d['Ngy vn hnh_Created'] || (d['Created Time'] ? getOperatingDateFromTimestamp(d['Created Time']) : ''));
        if (normCreatedDate === normActiveDate) {
          forecastOrdersNow += vol;
        } else {
          forecastOrdersLive += vol;
        }
        isForecastMember = true;
      }'''
    )

    # 2. Update final variables
    c = c.replace(
        '''  const finalShuttleForecast = isFutureDate ? 0 : (
    effectiveKpiSummary?.shuttle ?? forecastShuttle
  );

  const finalLinehaulForecast = isFutureDate ? 0 : (
    effectiveKpiSummary?.linehaul ?? forecastLinehaul
  );

  const totalForecast = isFutureDate ? 0 : (
    effectiveKpiSummary?.forecast_total ?? (finalShuttleForecast + finalLinehaulForecast)
  );''',
        '''  const finalOrdersNow = isFutureDate ? 0 : (
    effectiveKpiSummary?.orders_now ?? forecastOrdersNow
  );

  const finalOrdersLive = isFutureDate ? 0 : (
    effectiveKpiSummary?.orders_live ?? forecastOrdersLive
  );

  const totalForecast = isFutureDate ? 0 : (
    effectiveKpiSummary?.forecast_total ?? (finalOrdersNow + finalOrdersLive)
  );'''
    )

    # 3. Update HTML sub-rows
    c = c.replace(
        '''              <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                <span>Shuttle:</span>
                <strong style={{ color: '#a3e635', fontSize: '1.05rem' }}><NumberTicker value={finalShuttleForecast} /></strong>
              </div>
              <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                <span>Linehaul:</span>
                <strong style={{ color: '#f97316', fontSize: '1.05rem' }}><NumberTicker value={finalLinehaulForecast} /></strong>
              </div>''',
        '''              <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                <span>Orders Now:</span>
                <strong style={{ color: '#a3e635', fontSize: '1.05rem' }}><NumberTicker value={finalOrdersNow} /></strong>
              </div>
              <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                <span>Orders Live:</span>
                <strong style={{ color: '#f97316', fontSize: '1.05rem' }}><NumberTicker value={finalOrdersLive} /></strong>
              </div>'''
    )

    with open(fn, 'w', encoding='utf-8') as f:
        f.write(c)

    print(f"Successfully updated Forecast Card logic in {fn}")
