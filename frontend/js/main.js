/**
 * 应用入口：登录 / 会话恢复 / 页面切换 / 全局事件。
 * 页面逻辑都在 pages/ 下，这里只做装配，不写业务。
 */
import { api, auth } from './api.js';
import { $, $$, esc, toast } from './ui.js';
import { setUser, state } from './store.js';
import * as booking from './pages/booking.js';
import * as my from './pages/my.js';
import * as recommend from './pages/recommend.js';
import * as admin from './pages/admin.js';

const PAGES = {
  booking: { title: '预约座位', module: booking, adminOnly: false },
  mine: { title: '我的预约', module: my, adminOnly: false },
  recommend: { title: '智能推荐', module: recommend, adminOnly: false },
  admin: { title: '管理看板', module: admin, adminOnly: true },
};

let currentPage = 'booking';

function renderUser(user) {
  $('#userBadge').innerHTML = `<div class="user-card">
    <div class="avatar">${esc(String(user.name || user.username).slice(0, 1))}</div>
    <div><strong>${esc(user.name)}</strong><small>${user.role === 'admin' ? '系统管理员' : '学生用户'}</small></div>
  </div>`;
  $$('.admin-only').forEach((el) => el.classList.toggle('hidden', user.role !== 'admin'));
}

function switchPage(name) {
  if (!PAGES[name]) return;
  if (PAGES[name].adminOnly && state.user?.role !== 'admin') {
    name = 'booking';
  }
  currentPage = name;
  $$('.nav-item').forEach((el) => el.classList.toggle('active', el.dataset.page === name));
  $$('.page').forEach((el) => el.classList.add('hidden'));
  $(`#page-${name}`)?.classList.remove('hidden');
  $('#pageTitle').textContent = PAGES[name].title;
  PAGES[name].module.refresh?.();
}

function enterApp(user) {
  setUser(user);
  $('#loginView').classList.add('hidden');
  $('#appView').classList.remove('hidden');
  renderUser(user);
  switchPage(user.role === 'admin' ? 'admin' : 'booking');
}

function leaveApp(message) {
  setUser(null);
  auth.clear();
  $('#appView').classList.add('hidden');
  $('#loginView').classList.remove('hidden');
  $('#loginForm').reset();
  if (message) toast(message, 'error');
}

async function handleLogin(event) {
  event.preventDefault();
  const button = $('#loginForm button[type="submit"]');
  button.disabled = true;
  try {
    const data = await api.login($('#username').value.trim(), $('#password').value);
    auth.set(data.token);
    enterApp(data.user);
    toast('登录成功，欢迎回来');
  } catch (error) {
    toast(error.message, 'error');
  } finally {
    button.disabled = false;
  }
}

function bind() {
  $('#loginForm').addEventListener('submit', handleLogin);
  $('#logoutBtn').addEventListener('click', async () => {
    try {
      await api.logout();
    } catch {
      /* 令牌已失效也照常退出 */
    }
    leaveApp('已退出登录');
  });
  $$('.nav-item').forEach((el) => el.addEventListener('click', () => switchPage(el.dataset.page)));

  // 401：会话过期，回到登录页
  window.addEventListener('auth:expired', () => leaveApp('登录已过期，请重新登录'));
  // 任一页面发生写操作后，通知其他页面刷新
  window.addEventListener('data:changed', (event) => {
    const target = event.detail?.page;
    if (target && target !== currentPage) return;
    PAGES[currentPage]?.module.refresh?.();
  });
}

async function restoreSession() {
  if (!auth.token) return false;
  try {
    const data = await api.me();
    enterApp(data.user);
    return true;
  } catch {
    auth.clear();
    return false;
  }
}

async function main() {
  Object.values(PAGES).forEach((page) => page.module.init?.());
  bind();
  $('#todayLabel').textContent = new Date().toLocaleDateString('zh-CN', {
    year: 'numeric',
    month: 'long',
    day: 'numeric',
    weekday: 'long',
  });
  await restoreSession();
}

main();
