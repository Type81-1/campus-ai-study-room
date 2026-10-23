/** 极简前端状态容器：只保存当前用户与页面选择，避免全局变量散落。 */
export const state = {
  user: null,
  booking: { date: '', start: '09:00', end: '11:00' },
  seats: [],
  selectedSeat: null,
};

const listeners = new Map();

export function on(event, handler) {
  if (!listeners.has(event)) listeners.set(event, new Set());
  listeners.get(event).add(handler);
  return () => listeners.get(event)?.delete(handler);
}

export function emit(event, payload) {
  listeners.get(event)?.forEach((handler) => handler(payload));
}

export function setUser(user) {
  state.user = user;
  emit('user', user);
}

export function isAdmin() {
  return state.user?.role === 'admin';
}
