/**
 * DOM 小工具：选择器、转义、提示、时间选项、状态文案。
 * 不引入任何第三方库，整个前端保持零依赖（图表见 charts.js）。
 */
export const $ = (selector, root = document) => root.querySelector(selector);
export const $$ = (selector, root = document) => Array.from(root.querySelectorAll(selector));

export function esc(value) {
  return String(value ?? '').replace(/[&<>"']/g, (ch) => ({
    '&': '&amp;',
    '<': '&lt;',
    '>': '&gt;',
    '"': '&quot;',
    "'": '&#39;',
  }[ch]));
}

let toastTimer = null;
export function toast(message, kind = '') {
  const el = $('#toast');
  if (!el) return;
  el.textContent = message;
  el.className = `toast show ${kind}`.trim();
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => {
    el.className = 'toast';
  }, 2800);
}

export function todayISO() {
  const now = new Date();
  const offset = now.getTimezoneOffset() * 60000;
  return new Date(now.getTime() - offset).toISOString().slice(0, 10);
}

/** 生成 07:00 ~ 21:30 的半小时时段 */
export function timeOptions() {
  const list = [];
  for (let hour = 7; hour <= 21; hour += 1) {
    ['00', '30'].forEach((minute) => list.push(`${String(hour).padStart(2, '0')}:${minute}`));
  }
  return list;
}

export function fillTimeSelect(select, { value, from = 0, to }) {
  const options = timeOptions();
  const slice = options.slice(from, to ?? options.length);
  select.innerHTML = slice.map((t) => `<option value="${t}">${t}</option>`).join('');
  select.value = value ?? slice[0];
}

export const STATUS_LABEL = {
  booked: '待签到',
  checked_in: '学习中',
  completed: '已完成',
  cancelled: '已取消',
  expired: '已失效',
};

export const STATUS_CLASS = {
  booked: 'badge-warn',
  checked_in: 'badge-ok',
  completed: 'badge-ok',
  cancelled: 'badge-muted',
  expired: 'badge-danger',
};

export function statusBadge(status) {
  return `<span class="badge ${STATUS_CLASS[status] || 'badge-muted'}">${esc(STATUS_LABEL[status] || status)}</span>`;
}

export function formatDate(text) {
  if (!text) return '';
  const [year, month, day] = String(text).slice(0, 10).split('-');
  return `${month}-${day}`;
}

export function formatDateTime(text) {
  if (!text) return '—';
  return String(text).slice(0, 16).replace('T', ' ');
}

export function emptyState(text) {
  return `<div class="empty">${esc(text)}</div>`;
}

/** 骨架占位，避免请求期间页面空白 */
export function loading(rows = 3) {
  return Array.from({ length: rows })
    .map(() => '<div class="skeleton"></div>')
    .join('');
}
