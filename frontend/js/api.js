/**
 * 后端接口封装。
 * - 统一附带 Authorization: Bearer <token>
 * - 统一解析 { ok, message } 结构，失败抛 ApiError
 * - 401 时清理本地令牌并广播 auth:expired，交由 main.js 处理
 */
const TOKEN_KEY = 'studyRoomToken';

export const auth = {
  get token() {
    return localStorage.getItem(TOKEN_KEY);
  },
  set(token) {
    localStorage.setItem(TOKEN_KEY, token);
  },
  clear() {
    localStorage.removeItem(TOKEN_KEY);
  },
};

export class ApiError extends Error {
  constructor(message, status, code) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
    this.code = code;
  }
}

function buildUrl(path, query) {
  if (!query) return path;
  const params = new URLSearchParams();
  Object.entries(query).forEach(([key, value]) => {
    if (value !== undefined && value !== null && value !== '') params.set(key, value);
  });
  const qs = params.toString();
  return qs ? `${path}?${qs}` : path;
}

export async function request(path, { method = 'GET', body, query } = {}) {
  const headers = {};
  if (body !== undefined) headers['Content-Type'] = 'application/json';
  if (auth.token) headers.Authorization = `Bearer ${auth.token}`;

  let response;
  try {
    response = await fetch(buildUrl(path, query), {
      method,
      headers,
      body: body === undefined ? undefined : JSON.stringify(body),
    });
  } catch (error) {
    throw new ApiError('网络异常，请确认后端已启动', 0, 'network_error');
  }

  let data = {};
  const text = await response.text();
  if (text) {
    try {
      data = JSON.parse(text);
    } catch {
      data = { message: text.slice(0, 120) };
    }
  }

  if (!response.ok || data.ok === false) {
    if (response.status === 401 && auth.token) {
      auth.clear();
      window.dispatchEvent(new CustomEvent('auth:expired'));
    }
    throw new ApiError(data.message || `请求失败（HTTP ${response.status}）`, response.status, data.code);
  }
  return data;
}

export const api = {
  login: (username, password) => request('/api/login', { method: 'POST', body: { username, password } }),
  logout: () => request('/api/logout', { method: 'POST', body: {} }),
  me: () => request('/api/me'),

  seats: (date, start, end) => request('/api/seats', { query: { date, start, end } }),
  myReservations: () => request('/api/reservations'),
  createReservation: (payload) => request('/api/reservations', { method: 'POST', body: payload }),
  cancelReservation: (id) => request(`/api/reservations/${id}`, { method: 'DELETE' }),
  checkin: (id) => request(`/api/reservations/${id}/checkin`, { method: 'POST', body: {} }),
  checkout: (id) => request(`/api/reservations/${id}/checkout`, { method: 'POST', body: {} }),
  recommendations: (date, start, end) => request('/api/recommendations', { query: { date, start, end } }),

  stats: () => request('/api/admin/stats'),
  violations: () => request('/api/admin/violations'),
  scanViolations: () => request('/api/admin/violations/scan', { method: 'POST', body: {} }),
  resolveViolation: (id) => request(`/api/admin/violations/${id}/resolve`, { method: 'POST', body: {} }),
  users: () => request('/api/admin/users'),
  adminSeats: () => request('/api/admin/seats'),
  setSeatStatus: (id, status) =>
    request(`/api/admin/seats/${id}/status`, { method: 'POST', body: { status } }),
};
