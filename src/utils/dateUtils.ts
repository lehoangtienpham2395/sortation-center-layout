/**
 * dateUtils.ts — Robust Vietnam Timezone & Operating Date Utility
 * 
 * BẮT BUỘC KHÔNG DÙNG `new Date(new Date().toLocaleString())` vì sẽ tạo Invalid Date trên nhiều trình duyệt/HĐH.
 * Dùng Intl.DateTimeFormat 'en-CA' (format chuẩn ISO YYYY-MM-DD).
 */

export function getTodayOpDate(): string {
  try {
    const now = new Date();
    const fmt = new Intl.DateTimeFormat('en-CA', {
      timeZone: 'Asia/Ho_Chi_Minh',
      year: 'numeric',
      month: '2-digit',
      day: '2-digit',
      hour: '2-digit',
      minute: '2-digit',
      hourCycle: 'h23',
    });
    const formatted = fmt.format(now); // "2026-08-04, 11:09" hoặc "2026-08-04 11:09"
    const match = formatted.match(/(\d{4})-(\d{2})-(\d{2})[,\s]+(\d{2}):/);
    if (match) {
      const year  = parseInt(match[1], 10);
      const month = parseInt(match[2], 10) - 1; // 0-indexed
      const day   = parseInt(match[3], 10);
      const hour  = parseInt(match[4], 10);

      const d = new Date(year, month, day);
      if (hour < 6) {
        d.setDate(d.getDate() - 1);
      }
      const pad = (n: number) => String(n).padStart(2, '0');
      return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
    }
  } catch (e) {
    console.warn('getTodayOpDate error:', e);
  }
  return new Date().toISOString().split('T')[0];
}

export function getOperatingDateFromTimestamp(timestamp: string): string {
  if (!timestamp) return getTodayOpDate();
  const match = timestamp.match(/^(\d{4})-(\d{2})-(\d{2})[,\s]+(\d{2}):/);
  if (match) {
    const year  = parseInt(match[1], 10);
    const month = parseInt(match[2], 10) - 1;
    const day   = parseInt(match[3], 10);
    const hour  = parseInt(match[4], 10);

    const d = new Date(year, month, day);
    if (hour < 6) {
      d.setDate(d.getDate() - 1);
    }
    const pad = (n: number) => String(n).padStart(2, '0');
    return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
  }
  return timestamp.split(' ')[0] || getTodayOpDate();
}

export function getFormattedVietnamTime(): string {
  try {
    const now = new Date();
    const fmt = new Intl.DateTimeFormat('en-GB', {
      timeZone: 'Asia/Ho_Chi_Minh',
      year: 'numeric',
      month: '2-digit',
      day: '2-digit',
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit',
      hourCycle: 'h23',
    });
    return fmt.format(now).replace(',', '');
  } catch (_) {
    return new Date().toLocaleString();
  }
}
