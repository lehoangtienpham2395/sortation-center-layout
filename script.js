/**
 * ============================================================================
 * HCM HUB INBOUND DASHBOARD - BUSINESS LOGIC & DATA SYNCHRONIZATION
 * ============================================================================
 */

// ─── 1. MOCK DATA DEFINITIONS ───
const MOCK_DATA = {
  // Active Date: 2026-07-04 (Matches requirements 100%)
  "2026-07-04": {
    status: 200,
    kpi: {
      forecast: 5742,
      totalWeight: 38279,
      avgWeight: 9.38,
      inTransit: 37,
      arrival: 4081
    },
    hourlyTrend: {
      labels: [
        "06:00", "07:00", "08:00", "09:00", "10:00", "11:00", "12:00", "13:00", "14:00", "15:00", "16:00", "17:00", 
        "18:00", "19:00", "20:00", "21:00", "22:00", "23:00", "00:00", "01:00", "02:00", "03:00", "04:00", "05:00"
      ],
      forecast: [
        5, 25, 60, 110, 160, 220, 300, 450, 620, 880, 1050, 1010, 
        750, 520, 380, 150, 60, 15, 5, 2, 0, 0, 0, 0
      ],
      pickup: [
        0, 10, 45, 80, 120, 160, 210, 340, 480, 720, 850, 920, 
        810, 620, 450, 210, 100, 32, 15, 5, 0, 0, 0, 0
      ],
      arrival: [
        0, 0, 10, 30, 60, 90, 120, 240, 380, 510, 680, 790, 
        880, 910, 750, 420, 160, 85, 45, 20, 10, 0, 0, 0
      ]
    },
    selectionStatus: {
      arrival: { value: 4081, percentage: 71.1, color: "#00e5ff" },
      inTransit: { value: 1460, percentage: 25.4, color: "#0d8346" },
      pending: { value: 201, percentage: 3.5, color: "#475569" }
    },
    topStations: [
      { rank: 1, name: "FC-HCM BÌNH TÂN", vehicles: 8, orders: 1245, weight: "11,678" },
      { rank: 2, name: "FC-SG BẢY HIỀN", vehicles: 6, orders: 980, weight: "8,920" },
      { rank: 3, name: "FC-SG GÒ VẤP", vehicles: 5, orders: 742, weight: "6,910" },
      { rank: 4, name: "FC-BD BÌNH PHƯỚC", vehicles: 4, orders: 610, weight: "5,820" },
      { rank: 5, name: "FC-LA TÂN AN", vehicles: 3, orders: 520, weight: "4,950" },
      { rank: 6, name: "FC-TG MỸ THO", vehicles: 3, orders: 480, weight: "4,510" },
      { rank: 7, name: "FC-VL CHỢ LÁCH", vehicles: 3, orders: 412, weight: "3,890" },
      { rank: 8, name: "FC-CT LONG MỸ", vehicles: 2, orders: 320, weight: "2,980" },
      { rank: 9, name: "FC-AG AN PHÚ", vehicles: 2, orders: 258, weight: "2,420" },
      { rank: 10, name: "FC-YT CHÂU ĐỨC", vehicles: 1, orders: 175, weight: "1,201" }
    ],
    vehicles: [
      { plate: "51D-928.31", origin: "FC-BÌNH TÂN", orders: 450, weight: "4,210", eta: "10:15" },
      { plate: "50H-182.93", origin: "FC-GÒ VẤP", orders: 320, weight: "2,980", eta: "10:30" },
      { plate: "29C-551.02", origin: "FC-BẢY HIỀN", orders: 280, weight: "2,600", eta: "10:45" },
      { plate: "60F-882.17", origin: "FC-TÂN AN", orders: 210, weight: "1,950", eta: "11:00" },
      { plate: "65C-409.81", origin: "FC-MỸ THO", orders: 200, weight: "1,880", eta: "11:20" }
    ]
  },
  
  // Historical Date: 2026-07-03
  "2026-07-03": {
    status: 200,
    kpi: {
      forecast: 4850,
      totalWeight: 31525,
      avgWeight: 9.12,
      inTransit: 12,
      arrival: 3450
    },
    hourlyTrend: {
      labels: [
        "06:00", "07:00", "08:00", "09:00", "10:00", "11:00", "12:00", "13:00", "14:00", "15:00", "16:00", "17:00", 
        "18:00", "19:00", "20:00", "21:00", "22:00", "23:00", "00:00", "01:00", "02:00", "03:00", "04:00", "05:00"
      ],
      forecast: [
        2, 15, 35, 80, 120, 180, 250, 380, 520, 750, 890, 850, 
        620, 410, 290, 110, 40, 10, 2, 0, 0, 0, 0, 0
      ],
      pickup: [
        0, 5, 20, 60, 90, 130, 180, 290, 410, 610, 720, 810, 
        710, 520, 380, 150, 60, 10, 5, 0, 0, 0, 0, 0
      ],
      arrival: [
        0, 0, 5, 15, 30, 50, 90, 180, 290, 420, 550, 690, 
        760, 790, 610, 310, 90, 40, 20, 10, 0, 0, 0, 0
      ]
    },
    selectionStatus: {
      arrival: { value: 3450, percentage: 71.1, color: "#00e5ff" },
      inTransit: { value: 1100, percentage: 22.7, color: "#0d8346" },
      pending: { value: 300, percentage: 6.2, color: "#475569" }
    },
    topStations: [
      { rank: 1, name: "FC-HCM BÌNH TÂN", vehicles: 6, orders: 1010, weight: "9,210" },
      { rank: 2, name: "FC-SG BẢY HIỀN", vehicles: 5, orders: 840, weight: "7,600" },
      { rank: 3, name: "FC-SG GÒ VẤP", vehicles: 4, orders: 610, weight: "5,560" },
      { rank: 4, name: "FC-BD BÌNH PHƯỚC", vehicles: 3, orders: 500, weight: "4,600" },
      { rank: 5, name: "FC-LA TÂN AN", vehicles: 2, orders: 410, weight: "3,750" },
      { rank: 6, name: "FC-TG MỸ THO", vehicles: 2, orders: 390, weight: "3,550" },
      { rank: 7, name: "FC-VL CHỢ LÁCH", vehicles: 2, orders: 310, weight: "2,820" },
      { rank: 8, name: "FC-CT LONG MỸ", vehicles: 1, orders: 250, weight: "2,280" },
      { rank: 9, name: "FC-AG AN PHÚ", vehicles: 1, orders: 190, weight: "1,730" },
      { rank: 10, name: "FC-YT CHÂU ĐỨC", vehicles: 1, orders: 140, weight: "1,270" }
    ],
    vehicles: [
      { plate: "51D-401.99", origin: "FC-BÌNH TÂN", orders: 310, weight: "2,820", eta: "Đã đến" },
      { plate: "50H-992.11", origin: "FC-GÒ VẤP", orders: 250, weight: "2,280", eta: "Đã đến" },
      { plate: "29C-412.58", origin: "FC-BẢY HIỀN", orders: 190, weight: "1,730", eta: "18:40" },
      { plate: "60F-712.59", origin: "FC-TÂN AN", orders: 150, weight: "1,360", eta: "19:15" },
      { plate: "65C-123.45", origin: "FC-MỸ THO", orders: 140, weight: "1,270", eta: "20:00" }
    ]
  },
  
  // Empty State Date: 2026-07-02 (204 No Content)
  "2026-07-02": {
    status: 204, // No Content
    kpi: { forecast: 0, totalWeight: 0, avgWeight: 0, inTransit: 0, arrival: 0 },
    hourlyTrend: { labels: [], pickup: [], arrival: [] },
    selectionStatus: {
      arrival: { value: 0, percentage: 0, color: "#00e5ff" },
      inTransit: { value: 0, percentage: 0, color: "#0d8346" },
      pending: { value: 0, percentage: 0, color: "#475569" }
    },
    topStations: [],
    vehicles: []
  }
};

// ─── 2. STATE MANAGEMENT (Single Source of Truth) ───
let currentSelectedDate = "2026-07-04";
let lineChartInstance = null;
let donutChartInstance = null;

// Helper to format numbers with thousands separators
function formatNumber(num) {
  return num.toString().replace(/\B(?=(\d{3})+(?!\d))/g, ".");
}

// Helper to format weight with commas for thousands
function formatWeight(num) {
  return num.toString().replace(/\B(?=(\d{3})+(?!\d))/g, ",");
}

// ─── 3. UI RENDER FUNCTIONS ───

function updateDashboardUI(date) {
  const data = MOCK_DATA[date];
  const emptyStateOverlay = document.getElementById("emptyState");
  
  if (!data) return;

  // Handle HTTP 204 No Content / Empty State
  if (data.status === 204) {
    emptyStateOverlay.classList.add("active");
    // Reset KPI Card Display
    document.getElementById("val-forecast").innerText = "0";
    document.getElementById("val-weight").innerText = "0 kg";
    document.getElementById("sub-weight").innerText = "Avg weight: 0.00 kg/pkg";
    document.getElementById("val-transit").innerText = "0";
    document.getElementById("val-arrival").innerText = "0";
    document.getElementById("donut-total").innerText = "0";
    
    // Clear tables
    document.querySelector("#stationsTable tbody").innerHTML = `
      <tr>
        <td colspan="5" style="text-align: center; color: var(--text-muted); padding: 30px;">Không có dữ liệu trạm gửi</td>
      </tr>
    `;
    document.querySelector("#vehiclesTable tbody").innerHTML = `
      <tr>
        <td colspan="5" style="text-align: center; color: var(--text-muted); padding: 30px;">Không có xe đang vận chuyển</td>
      </tr>
    `;
    
    // Update Ticker
    updateTicker(0);
    return;
  } else {
    emptyStateOverlay.classList.remove("active");
  }

  // 1. Update KPI cards
  const kpi = data.kpi;
  document.getElementById("val-forecast").innerText = formatNumber(kpi.forecast);
  document.getElementById("val-weight").innerText = `${formatWeight(kpi.totalWeight)} kg`;
  document.getElementById("sub-weight").innerText = `Avg weight: ${kpi.avgWeight.toFixed(2)} kg/pkg`;
  document.getElementById("val-transit").innerText = formatNumber(kpi.inTransit);
  document.getElementById("val-arrival").innerText = formatNumber(kpi.arrival);

  // 2. Update Charts
  renderLineChart(data.hourlyTrend);
  renderDonutChart(data.selectionStatus, kpi.forecast);

  // 3. Update Tables
  renderStationsTable(data.topStations);
  renderVehiclesTable(data.vehicles);

  // 4. Update Ticker (Synchronized Total Orders)
  updateTicker(kpi.forecast);
}

function updateTicker(totalOrders) {
  const ticker = document.getElementById("footerTicker");
  const formattedVal = formatNumber(totalOrders);
  ticker.innerHTML = `
    [10:08] HỆ THỐNG ỔN ĐỊNH // KHÔNG CÓ CẢNH BÁO // TỔNG SẢN LƯỢNG QUẢN LÝ: ${formattedVal} ĐƠN. &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;
    [10:08] HỆ THỐNG ỔN ĐỊNH // KHÔNG CÓ CẢNH BÁO // TỔNG SẢN LƯỢNG QUẢN LÝ: ${formattedVal} ĐƠN.
  `;
}

function renderStationsTable(stations) {
  const tbody = document.querySelector("#stationsTable tbody");
  tbody.innerHTML = "";
  
  if (stations.length === 0) {
    tbody.innerHTML = `<tr><td colspan="5" style="text-align: center; color: var(--text-muted);">Không có dữ liệu</td></tr>`;
    return;
  }

  stations.forEach(st => {
    const tr = document.createElement("tr");
    tr.innerHTML = `
      <td class="highlight-val">${st.rank}</td>
      <td class="highlight-val" style="font-weight: 600;">${st.name}</td>
      <td style="text-align: right;">${st.vehicles}</td>
      <td class="highlight-purple" style="text-align: right;">${formatNumber(st.orders)}</td>
      <td class="highlight-val" style="text-align: right;">${st.weight} kg</td>
    `;
    tbody.appendChild(tr);
  });
}

function renderVehiclesTable(vehicles) {
  const tbody = document.querySelector("#vehiclesTable tbody");
  tbody.innerHTML = "";

  if (vehicles.length === 0) {
    tbody.innerHTML = `<tr><td colspan="5" style="text-align: center; color: var(--text-muted);">Không có xe</td></tr>`;
    return;
  }

  vehicles.forEach(vh => {
    const tr = document.createElement("tr");
    tr.innerHTML = `
      <td class="highlight-val" style="font-family: monospace; font-size: 0.85rem; font-weight: 700;">${vh.plate}</td>
      <td>${vh.origin}</td>
      <td class="highlight-purple" style="text-align: right;">${formatNumber(vh.orders)}</td>
      <td class="highlight-val" style="text-align: right;">${formatWeight(vh.weight)} kg</td>
      <td class="highlight-green" style="text-align: center; font-weight: 600;">${vh.eta}</td>
    `;
    tbody.appendChild(tr);
  });
}

// ─── 4. CHART.JS INTEGRATION ───

function renderLineChart(trendData) {
  const ctx = document.getElementById("hourlyTrendChart").getContext("2d");
  
  if (lineChartInstance) {
    lineChartInstance.destroy();
  }

  // If there's no data (e.g. 204), don't draw anything
  if (!trendData.labels || trendData.labels.length === 0) return;

  // Create neon gradients
  const forecastGrad = ctx.createLinearGradient(0, 0, 0, 220);
  forecastGrad.addColorStop(0, 'rgba(249, 115, 22, 0.22)');
  forecastGrad.addColorStop(1, 'rgba(249, 115, 22, 0)');

  const pickupGrad = ctx.createLinearGradient(0, 0, 0, 220);
  pickupGrad.addColorStop(0, 'rgba(13, 131, 70, 0.22)');
  pickupGrad.addColorStop(1, 'rgba(13, 131, 70, 0)');

  const inboundGrad = ctx.createLinearGradient(0, 0, 0, 220);
  inboundGrad.addColorStop(0, 'rgba(0, 229, 255, 0.22)');
  inboundGrad.addColorStop(1, 'rgba(0, 229, 255, 0)');

  lineChartInstance = new Chart(ctx, {
    type: 'line',
    data: {
      labels: trendData.labels,
      datasets: [
        {
          label: 'Dự báo (Forecast)',
          data: trendData.forecast,
          borderColor: '#f97316',
          backgroundColor: forecastGrad,
          borderWidth: 3,
          tension: 0.4,
          fill: true,
          pointBackgroundColor: '#ffffff',
          pointBorderColor: '#f97316',
          pointBorderWidth: 2,
          pointHoverRadius: 8,
          pointRadius: 4,
          pointHoverBackgroundColor: '#ffffff',
          pointHoverBorderWidth: 3
        },
        {
          label: 'Gom (Pickup)',
          data: trendData.pickup,
          borderColor: '#0d8346',
          backgroundColor: pickupGrad,
          borderWidth: 3,
          tension: 0.4,
          fill: true,
          pointBackgroundColor: '#ffffff',
          pointBorderColor: '#0d8346',
          pointBorderWidth: 2,
          pointHoverRadius: 8,
          pointRadius: 4,
          pointHoverBackgroundColor: '#ffffff',
          pointHoverBorderWidth: 3
        },
        {
          label: 'Nhập (Inbound)',
          data: trendData.arrival,
          borderColor: '#00e5ff',
          backgroundColor: inboundGrad,
          borderWidth: 3,
          tension: 0.4,
          fill: true,
          pointBackgroundColor: '#ffffff',
          pointBorderColor: '#00e5ff',
          pointBorderWidth: 2,
          pointHoverRadius: 8,
          pointRadius: 4,
          pointHoverBackgroundColor: '#ffffff',
          pointHoverBorderWidth: 3
        }
      ]
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: {
          display: false // We use our custom HTML legend
        },
        tooltip: {
          mode: 'index',
          intersect: false,
          backgroundColor: '#1e293b',
          titleFont: { family: 'Outfit', size: 13, weight: 'bold' },
          bodyFont: { family: 'Outfit', size: 12 },
          borderColor: 'rgba(255,255,255,0.08)',
          borderWidth: 1,
          padding: 10
        }
      },
      scales: {
        x: {
          grid: {
            color: 'rgba(255,255,255,0.03)',
            drawBorder: false
          },
          ticks: {
            color: '#64748b',
            font: { family: 'Outfit', size: 11 }
          }
        },
        y: {
          grid: {
            color: 'rgba(255,255,255,0.05)',
            drawBorder: false
          },
          ticks: {
            color: '#64748b',
            font: { family: 'Outfit', size: 11 }
          }
        }
      }
    }
  });
}

function renderDonutChart(statusData, totalCount) {
  const ctx = document.getElementById("selectionStatusChart").getContext("2d");
  
  if (donutChartInstance) {
    donutChartInstance.destroy();
  }

  // Update center total label
  document.getElementById("donut-total").innerText = formatNumber(totalCount);

  const keys = Object.keys(statusData);
  const chartLabels = ["Đã nhập kho (Inbound)", "Đang trên đường", "Chờ xử lý"];
  const chartValues = keys.map(k => statusData[k].value);
  const chartColors = keys.map(k => statusData[k].color);

  donutChartInstance = new Chart(ctx, {
    type: 'doughnut',
    data: {
      labels: chartLabels,
      datasets: [{
        data: chartValues,
        backgroundColor: chartColors,
        borderWidth: 0,
        hoverOffset: 4
      }]
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      cutout: '76%',
      plugins: {
        legend: {
          display: false
        },
        tooltip: {
          backgroundColor: '#1e293b',
          titleFont: { family: 'Outfit', size: 13, weight: 'bold' },
          bodyFont: { family: 'Outfit', size: 12 },
          padding: 10,
          callbacks: {
            label: function(context) {
              const val = context.raw;
              const total = context.dataset.data.reduce((a, b) => a + b, 0);
              const pct = total > 0 ? ((val / total) * 100).toFixed(1) : 0;
              return ` ${context.label}: ${formatNumber(val)} (${pct}%)`;
            }
          }
        }
      }
    }
  });

  // Render Custom Donut Legend Below
  const legendContainer = document.getElementById("donutLegend");
  legendContainer.innerHTML = "";

  const labelMappings = {
    arrival: "Đã nhập kho (Inbound)",
    inTransit: "Đang trên đường",
    pending: "Chờ xử lý"
  };

  keys.forEach(k => {
    const item = statusData[k];
    const legendItem = document.createElement("div");
    legendItem.className = "donut-legend-item";
    legendItem.innerHTML = `
      <div class="donut-legend-header">
        <span class="donut-legend-dot" style="background-color: ${item.color}; box-shadow: 0 0 6px ${item.color};"></span>
        <span class="label-text">${labelMappings[k]}</span>
      </div>
      <div class="donut-legend-value">${formatNumber(item.value)}</div>
      <div class="donut-legend-pct">${item.percentage}%</div>
    `;
    legendContainer.appendChild(legendItem);
  });
}

// ─── 5. DYNAMIC 30-DAY GENERATION & INTERACTION LOGIC ───

// Generates dynamic mock data for dates that aren't hardcoded
function generateDynamicMockData(dateStr) {
  // Let's decide if this date is simulated as Empty (204)
  // Let's make every 5th date empty for demonstration (e.g., date ending in 0 or 5, or based on date hash)
  const dayVal = parseInt(dateStr.split("-")[2], 10);
  if (dayVal % 7 === 0 || dateStr === "2026-07-02") {
    MOCK_DATA[dateStr] = {
      status: 204,
      kpi: { forecast: 0, totalWeight: 0, avgWeight: 0, inTransit: 0, arrival: 0 },
      hourlyTrend: { labels: [], pickup: [], arrival: [] },
      selectionStatus: {
        arrival: { value: 0, percentage: 0, color: "#10b981" },
        inTransit: { value: 0, percentage: 0, color: "#8b5cf6" },
        pending: { value: 0, percentage: 0, color: "#475569" }
      },
      topStations: [],
      vehicles: []
    };
    return;
  }

  // Generate realistic positive operational data
  const seed = dayVal * 150;
  const forecast = 4000 + (seed % 2500);
  const arrival = Math.floor(forecast * (0.65 + (seed % 15) / 100));
  const inTransit = Math.floor((forecast - arrival) * 0.88);
  const pending = forecast - arrival - inTransit;
  
  const totalWeight = forecast * (8.5 + (seed % 20) / 10);
  const avgWeight = totalWeight / forecast;
  const vehiclesCount = 15 + (seed % 30);

  // Hourly arrays
  const labels = [
    "06:00", "07:00", "08:00", "09:00", "10:00", "11:00", "12:00", "13:00", "14:00", "15:00", "16:00", "17:00", 
    "18:00", "19:00", "20:00", "21:00", "22:00", "23:00", "00:00", "01:00", "02:00", "03:00", "04:00", "05:00"
  ];
  const forecastTrend = labels.map((_, i) => {
    if (i < 5) return Math.floor(forecast * 0.015);
    if (i < 13) return Math.floor(forecast * (0.07 + Math.sin(i / 3) * 0.06));
    if (i < 18) return Math.floor(forecast * 0.09);
    return Math.floor(forecast * 0.03);
  });
  const pickup = labels.map((_, i) => {
    if (i < 5) return Math.floor(forecast * 0.01);
    if (i < 13) return Math.floor(forecast * (0.05 + Math.sin(i / 3) * 0.05));
    if (i < 18) return Math.floor(forecast * 0.08);
    return Math.floor(forecast * 0.02);
  });
  const arrivalTrend = labels.map((_, i) => {
    if (i < 7) return 0;
    if (i < 15) return Math.floor(arrival * (0.04 + Math.sin((i - 2) / 3) * 0.03));
    if (i < 20) return Math.floor(arrival * 0.09);
    return Math.floor(arrival * 0.03);
  });

  MOCK_DATA[dateStr] = {
    status: 200,
    kpi: {
      forecast,
      totalWeight: Math.round(totalWeight),
      avgWeight,
      inTransit: vehiclesCount,
      arrival
    },
    hourlyTrend: { labels, forecast: forecastTrend, pickup, arrival: arrivalTrend },
    selectionStatus: {
      arrival: { value: arrival, percentage: parseFloat(((arrival / forecast) * 100).toFixed(1)), color: "#00e5ff" },
      inTransit: { value: inTransit, percentage: parseFloat(((inTransit / forecast) * 100).toFixed(1)), color: "#0d8346" },
      pending: { value: pending, percentage: parseFloat(((pending / forecast) * 100).toFixed(1)), color: "#475569" }
    },
    topStations: [
      { rank: 1, name: "FC-HCM BÌNH TÂN", vehicles: Math.round(vehiclesCount * 0.2), orders: Math.round(forecast * 0.25), weight: formatWeight(Math.round(totalWeight * 0.25)) },
      { rank: 2, name: "FC-SG BẢY HIỀN", vehicles: Math.round(vehiclesCount * 0.15), orders: Math.round(forecast * 0.18), weight: formatWeight(Math.round(totalWeight * 0.18)) },
      { rank: 3, name: "FC-SG GÒ VẤP", vehicles: Math.round(vehiclesCount * 0.12), orders: Math.round(forecast * 0.15), weight: formatWeight(Math.round(totalWeight * 0.15)) },
      { rank: 4, name: "FC-BD BÌNH PHƯỚC", vehicles: Math.round(vehiclesCount * 0.1), orders: Math.round(forecast * 0.12), weight: formatWeight(Math.round(totalWeight * 0.12)) },
      { rank: 5, name: "FC-LA TÂN AN", vehicles: Math.round(vehiclesCount * 0.08), orders: Math.round(forecast * 0.1), weight: formatWeight(Math.round(totalWeight * 0.1)) }
    ],
    vehicles: [
      { plate: `51D-${100 + (seed%800)}.${seed%99}`, origin: "FC-BÌNH TÂN", orders: Math.round(forecast * 0.05), weight: Math.round(totalWeight * 0.05), eta: "14:20" },
      { plate: `50H-${200 + (seed%600)}.${seed%90}`, origin: "FC-GÒ VẤP", orders: Math.round(forecast * 0.04), weight: Math.round(totalWeight * 0.04), eta: "15:00" }
    ]
  };
}

// Generate list of last 30 days starting from 2026-07-04 backwards
function get30DaysList() {
  const days = [];
  const baseDate = new Date(2026, 6, 4); // July 4, 2026 (Month is 0-indexed: June=5, July=6)
  
  for (let i = 0; i < 30; i++) {
    const targetDate = new Date(baseDate);
    targetDate.setDate(baseDate.getDate() - i);
    
    const year = targetDate.getFullYear();
    const month = String(targetDate.getMonth() + 1).padStart(2, '0');
    const day = String(targetDate.getDate()).padStart(2, '0');
    days.push(`${year}-${month}-${day}`);
  }
  return days;
}

// Initialize Custom Datepicker dropdown content
function initDatePicker() {
  const datepicker = document.getElementById("customDatePicker");
  const trigger = document.getElementById("datepickerTrigger");
  const dropdown = document.getElementById("datepickerDropdown");
  const listContainer = document.getElementById("datepickerList");
  const selectedText = document.getElementById("selectedDateText");

  // Get the 30 days
  const dates = get30DaysList();

  // Populate list
  listContainer.innerHTML = "";
  dates.forEach(d => {
    // Generate mock data for dates on-the-fly if not already present
    if (!MOCK_DATA[d]) {
      generateDynamicMockData(d);
    }

    const item = MOCK_DATA[d];
    const button = document.createElement("button");
    button.className = `datepicker-item ${d === currentSelectedDate ? 'active' : ''}`;
    button.setAttribute("data-date", d);
    
    // Display dates nicely (e.g. today/yesterday markings)
    let displayLabel = d;
    if (d === "2026-07-04") displayLabel = "2026-07-04 (Hôm nay)";
    if (d === "2026-07-03") displayLabel = "2026-07-03 (Hôm qua)";

    // Add visual empty state indicator
    const is204 = item.status === 204;
    button.innerHTML = `
      <span>${displayLabel}</span>
      ${is204 ? '<span class="badge-empty">Trống (204)</span>' : ''}
    `;

    button.addEventListener("click", () => {
      selectDate(d);
    });

    listContainer.appendChild(button);
  });

  // Toggle Dropdown open/close
  trigger.addEventListener("click", (e) => {
    e.stopPropagation();
    datepicker.classList.toggle("open");
  });

  // Presets Handlers
  const todayBtn = dropdown.querySelector("[data-preset='today']");
  const yesterdayBtn = dropdown.querySelector("[data-preset='yesterday']");

  todayBtn.addEventListener("click", (e) => {
    e.stopPropagation();
    selectDate("2026-07-04");
  });

  yesterdayBtn.addEventListener("click", (e) => {
    e.stopPropagation();
    selectDate("2026-07-03");
  });

  // Close dropdown on click outside
  document.addEventListener("click", (e) => {
    if (!datepicker.contains(e.target)) {
      datepicker.classList.remove("open");
    }
  });

  function selectDate(dateStr) {
    currentSelectedDate = dateStr;
    selectedText.innerText = dateStr;
    
    // Update active class in list
    const items = listContainer.querySelectorAll(".datepicker-item");
    items.forEach(it => {
      if (it.getAttribute("data-date") === dateStr) {
        it.classList.add("active");
      } else {
        it.classList.remove("active");
      }
    });

    datepicker.classList.remove("open");
    updateDashboardUI(dateStr);
  }
}

// ─── 6. INITIALIZATION ON LOAD ───

document.addEventListener("DOMContentLoaded", () => {
  // Initialize Date picker
  initDatePicker();
  
  // Initial dashboard load
  updateDashboardUI(currentSelectedDate);
});

