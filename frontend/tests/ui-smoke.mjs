/**
 * 前端冒烟测试（jsdom）：加载真实 index.html + 真实 ES 模块，模拟点击走一遍主流程。
 *
 * 目的：在没有浏览器的环境下验证选择器、事件绑定、渲染逻辑是否真的跑得通。
 * 依赖只有 jsdom（devDependency），不影响后端与页面运行。
 *
 * 用法：
 *   1) 先启动后端：python backend/server.py   （另开一个终端）
 *   2) 灌入演示数据：python scripts/seed_demo.py
 *   3) cd frontend/tests && npm install && BASE_URL=http://127.0.0.1:8000 node ui-smoke.mjs
 */
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { JSDOM } from 'jsdom';

const HERE = path.dirname(fileURLToPath(import.meta.url));
const BASE = process.env.BASE_URL || 'http://127.0.0.1:8000';
const failures = [];

function check(name, condition, detail = '') {
  if (condition) {
    console.log(`  [通过] ${name}`);
  } else {
    failures.push(name);
    console.log(`  [失败] ${name} ${detail}`);
  }
}

const wait = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

async function waitFor(label, predicate, timeout = 6000) {
  const started = Date.now();
  while (Date.now() - started < timeout) {
    try {
      if (predicate()) return true;
    } catch {
      /* 元素还没渲染 */
    }
    await wait(80);
  }
  throw new Error(`等待超时：${label}`);
}

async function loginToken(username, password) {
  const response = await fetch(`${BASE}/api/login`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ username, password }),
  });
  const data = await response.json();
  return data.token;
}

async function main() {
  const html = fs.readFileSync(path.join(HERE, '..', 'index.html'), 'utf8');
  const dom = new JSDOM(html, { url: `${BASE}/`, pretendToBeVisual: true });
  const { window } = dom;

  // 把 jsdom 的宿主对象挂到 node 全局，供 ES 模块直接使用
  global.window = window;
  global.document = window.document;
  global.localStorage = window.localStorage;
  global.CustomEvent = window.CustomEvent;
  global.Event = window.Event;
  global.HTMLElement = window.HTMLElement;
  global.Node = window.Node;
  const realFetch = globalThis.fetch;
  const wrappedFetch = (url, options) =>
    realFetch(typeof url === 'string' && url.startsWith('/') ? BASE + url : url, options);
  global.fetch = wrappedFetch;
  window.fetch = wrappedFetch;
  window.confirm = () => true;

  // 预置管理员令牌，走「会话恢复」路径，直接进入管理看板
  window.localStorage.setItem('studyRoomToken', await loginToken('admin', 'admin123'));

  console.log('\n== 1. 会话恢复 + 管理看板 ==');
  await import('../js/main.js');
  await waitFor('管理看板渲染', () => !window.document.getElementById('appView').classList.contains('hidden'));
  check('会话恢复后进入主界面', !window.document.getElementById('appView').classList.contains('hidden'));
  check('管理看板默认打开', window.document.getElementById('page-admin').className.indexOf('hidden') === -1);

  await waitFor('统计卡片', () => window.document.querySelectorAll('#statsCards .stat-card').length >= 6);
  check('统计卡片 6 个', window.document.querySelectorAll('#statsCards .stat-card').length === 6);

  await waitFor('趋势图', () => window.document.querySelector('#trendChart svg'));
  check('趋势折线图已渲染', !!window.document.querySelector('#trendChart svg polyline'));
  check('热门座位排行已渲染', !!window.document.querySelector('#popularChart .rank-row'));
  check('时段环形图已渲染', !!window.document.querySelector('#slotChart svg circle'));

  console.log('\n== 2. 管理看板页签 ==');
  const clickTab = (name) =>
    window.document.querySelector(`[data-tab="${name}"]`).dispatchEvent(new window.Event('click', { bubbles: true }));

  clickTab('violations');
  await waitFor('违规表格', () => window.document.querySelectorAll('#adminViolations tbody tr').length > 0);
  check('违规表格有数据', window.document.querySelectorAll('#adminViolations tbody tr').length >= 1);
  check('违规记录显示类型徽标', !!window.document.querySelector('#adminViolations .badge-danger'));

  clickTab('seats');
  await waitFor('座位表格', () => window.document.querySelectorAll('#adminSeats tbody tr').length === 24);
  check('座位管理 24 行', window.document.querySelectorAll('#adminSeats tbody tr').length === 24);

  clickTab('users');
  await waitFor('用户表格', () => window.document.querySelectorAll('#adminUsers tbody tr').length >= 3);
  check('用户概览含统计列', window.document.querySelectorAll('#adminUsers tbody tr').length >= 3);

  console.log('\n== 3. 座位维护开关 ==');
  clickTab('seats');
  await waitFor('座位表格', () => window.document.querySelectorAll('#adminSeats tbody tr').length === 24);
  const toggle = window.document.querySelector('#adminSeats [data-seat]');
  toggle.dispatchEvent(new window.Event('click', { bubbles: true }));
  await waitFor('状态切换生效', () => window.document.querySelector('#adminSeats .badge-danger'));
  check('座位可切换为维护中', !!window.document.querySelector('#adminSeats .badge-danger'));
  const restore = window.document.querySelector('#adminSeats [data-next="available"]');
  if (restore) {
    restore.dispatchEvent(new window.Event('click', { bubbles: true }));
    await wait(400);
  }

  console.log('\n== 4. 退出并以学生身份重新登录 ==');
  window.document.getElementById('logoutBtn').dispatchEvent(new window.Event('click', { bubbles: true }));
  await waitFor('回到登录页', () => !window.document.getElementById('loginView').classList.contains('hidden'));
  check('退出后回到登录页', !window.document.getElementById('loginView').classList.contains('hidden'));
  check('退出后令牌被清理', !window.localStorage.getItem('studyRoomToken'));

  window.document.getElementById('username').value = 'student001';
  window.document.getElementById('password').value = '123456';
  window.document
    .getElementById('loginForm')
    .dispatchEvent(new window.Event('submit', { bubbles: true, cancelable: true }));

  await waitFor('登录成功进入主界面', () => !window.document.getElementById('appView').classList.contains('hidden'));
  check('学生登录成功', !!window.localStorage.getItem('studyRoomToken'));
  check('学生看不到管理菜单', window.document.querySelector('.nav-item[data-page="admin"]').classList.contains('hidden'));
  check('学生默认进入预约页', window.document.getElementById('pageTitle').textContent === '预约座位');

  console.log('\n== 5. 预约页渲染与弹窗 ==');
  await waitFor('座位网格', () => window.document.querySelectorAll('#seatGrid .seat-card').length === 24);
  check('座位网格 24 个', window.document.querySelectorAll('#seatGrid .seat-card').length === 24);
  check('可预约数量已更新', window.document.getElementById('availableCount').textContent !== '—');

  const seat = window.document.querySelector('#seatGrid .seat-card.available');
  seat.dispatchEvent(new window.Event('click', { bubbles: true }));
  check('点击座位弹出详情', !window.document.getElementById('seatModal').classList.contains('hidden'));
  check('弹窗显示座位号', window.document.getElementById('seatModal').textContent.length > 0);
  window.document.querySelector('#seatModal [data-close]').dispatchEvent(new window.Event('click', { bubbles: true }));

  console.log('\n== 6. 我的预约与智能推荐 ==');
  window.document
    .querySelector('.nav-item[data-page="mine"]')
    .dispatchEvent(new window.Event('click', { bubbles: true }));
  await waitFor('预约列表', () => window.document.querySelectorAll('#reservationList .reservation-item').length > 0);
  check('我的预约有记录', window.document.querySelectorAll('#reservationList .reservation-item').length > 0);
  check('显示状态徽标', !!window.document.querySelector('#reservationList .badge'));
  check('显示可签到时段提示', window.document.getElementById('reservationList').textContent.includes('可签到时段'));

  window.document
    .querySelector('.nav-item[data-page="recommend"]')
    .dispatchEvent(new window.Event('click', { bubbles: true }));
  await waitFor('推荐列表', () => window.document.querySelectorAll('#recommendList .recommend-item').length > 0);
  check('推荐列表有结果', window.document.querySelectorAll('#recommendList .recommend-item').length > 0);

  console.log(`\n===== 结果：${failures.length === 0 ? '全部通过' : `${failures.length} 项失败`} =====`);
  if (failures.length) {
    console.log(failures.map((name) => ` - ${name}`).join('\n'));
    process.exitCode = 1;
  }
  window.close();
}

main().catch((error) => {
  console.error('测试中断：', error);
  process.exitCode = 1;
});
