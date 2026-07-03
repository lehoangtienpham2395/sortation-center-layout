const fs = require('fs');
const path = require('path');

// 1. Read react keys
const reactKeys = JSON.parse(fs.readFileSync('react_keys.json', 'utf8'));

// 2. Read valid.csv
const csvPath = path.join('backend_sync', 'config', 'valid.csv');
const csvContent = fs.readFileSync(csvPath, 'utf8');
const csvLines = csvContent.split('\n').map(l => l.trim()).filter(l => l.length > 0);
const headers = csvLines[0].split(',').map(h => h.trim());
const colNameIdx = headers.indexOf('Bưu cục final');
const colAreaIdx = headers.indexOf('area');
const colNameFallbackIdx = headers.indexOf('Bưu cục');

const sheetList = [];
for (let i = 1; i < csvLines.length; i++) {
  const cols = csvLines[i].split(',').map(c => c.trim());
  if (cols.length < 2) continue;
  const area = cols[colAreaIdx] || '';
  const name = cols[colNameIdx] || cols[colNameFallbackIdx] || '';
  if (!area || !name || name.toLowerCase() === 'nan' || area === 'offline') continue;
  
  // Find matching zone from reactKeys using areaId
  const matchReact = reactKeys.find(rk => rk.areaId.toUpperCase() === area.toUpperCase());
  const zone = matchReact ? matchReact.zone : '1';
  
  sheetList.push({
    areaId: area,
    name: name,
    zone: zone,
    key: zone + '_' + area
  });
}

// Write the complete audit table to markdown for printing
const audit = [];
let matchCount = 0;
let mismatchCount = 0;

reactKeys.forEach(rk => {
  const matchSheet = sheetList.find(sk => sk.key.toUpperCase() === rk.key.toUpperCase());
  let status = 'Match';
  let reason = '';
  
  if (!matchSheet) {
    status = 'No Match';
    const sameArea = sheetList.find(sk => sk.areaId.toUpperCase() === rk.areaId.toUpperCase());
    if (sameArea) {
      reason = 'Khác zone (Sheet: ' + sameArea.zone + ', React: ' + rk.zone + ')';
    } else {
      reason = 'Không tồn tại trên sheet Config';
    }
    mismatchCount++;
  } else {
    if (matchSheet.key !== rk.key) {
      status = 'Mismatch Casing/Spacing';
      reason = 'Khác chữ hoa/thường (Sheet: ' + matchSheet.key + ', React: ' + rk.key + ')';
      mismatchCount++;
    } else {
      matchCount++;
    }
  }
  
  audit.push({
    reactKey: rk.key,
    sheetKey: matchSheet ? matchSheet.key : 'N/A',
    reactName: rk.name,
    sheetName: matchSheet ? matchSheet.name : 'N/A',
    status: status,
    reason: reason
  });
});

let md = '| Key từ Google Sheet | Key React | Match | Lý do (nếu lệch) |\n| --- | --- | --- | --- |\n';
audit.forEach(a => {
  md += '| ' + a.sheetKey + ' | ' + a.reactKey + ' | ' + (a.status === 'Match' ? 'Match' : 'No Match') + ' | ' + a.reason + ' |\n';
});

console.log('---TABLE_MD---');
console.log(md);
console.log('---TOTALS---');
console.log('Total React:', reactKeys.length);
console.log('Total Sheet:', sheetList.length);
console.log('Matches:', matchCount);
console.log('Mismatches:', mismatchCount);
