/**
 * SSE 实时通道：订阅后端的座位/预约/违规事件，驱动页面自动刷新。
 *
 * - EventSource 不能自定义请求头，因此令牌放在查询串里（后端也支持 Bearer 头）；
 * - 浏览器会自动重连（retry: 3000），这里只负责更新连接状态指示；
 * - 不支持 EventSource 的环境（如 jsdom 测试）直接跳过，不影响主流程。
 */
import { auth } from './api.js';

const EVENTS = [
  'reservation.created',
  'reservation.cancelled',
  'reservation.checked_in',
  'reservation.checked_out',
  'seat.status',
  'violation.scanned',
  'violation.resolved',
];

let source = null;
const listeners = new Set();

export function subscribe(handler) {
  listeners.add(handler);
  return () => listeners.delete(handler);
}

function setStatus(state) {
  const badge = document.getElementById('realtimeBadge');
  if (!badge) return;
  const labels = { online: '实时已连接', offline: '实时重连中', off: '实时未连接' };
  badge.textContent = state === 'online' ? '实时' : '离线';
  badge.className = `live-badge ${state}`;
  badge.title = labels[state] || '';
}

export function connect() {
  if (source || !auth.token) return;
  // 用 window 上的构造器判断：Node / jsdom 环境没有浏览器版 EventSource
  const Ctor = typeof window !== 'undefined' ? window.EventSource : undefined;
  if (typeof Ctor !== 'function') {
    setStatus('off');
    return;
  }

  source = new Ctor(`/api/events?token=${encodeURIComponent(auth.token)}`);

  source.onopen = () => setStatus('online');
  source.onerror = () => setStatus('offline');

  EVENTS.forEach((type) => {
    source.addEventListener(type, (event) => {
      let payload = {};
      try {
        payload = JSON.parse(event.data);
      } catch {
        payload = {};
      }
      listeners.forEach((handler) => {
        try {
          handler({ type, payload });
        } catch (error) {
          console.warn('实时事件处理失败', type, error);
        }
      });
    });
  });
}

export function disconnect() {
  if (source) {
    source.close();
    source = null;
  }
  setStatus('off');
}

export function isConnected() {
  return Boolean(source) && source.readyState === 1;
}
