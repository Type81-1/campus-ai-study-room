/**
 * 管理看板：概览图表 / 违规预警 / 座位维护 / 用户概览。
 * 四块内容用页签切换，避免单页过长。
 */
import { api } from '../api.js';
import { $, $$, emptyState, esc, formatDate, formatDateTime, loading, statusBadge, toast } from '../ui.js';
import { renderBars, renderDonut, renderLine, renderRankBars } from '../charts.js';

let refs = null;
let currentTab = 'overview';

export function init() {
  refs = {
    tabs: $('#adminTabs'),
    overview: $('#adminOverview'),
    violations: $('#adminViolations'),
    seats: $('#adminSeats'),
    users: $('#adminUsers'),
    refresh: $('#adminRefresh'),
    scan: $('#scanViolations'),
  };

  refs.tabs.addEventListener('click', (event) => {
    const tab = event.target.closest('[data-tab]');
    if (!tab) return;
    switchTab(tab.dataset.tab);
  });
  refs.refresh.addEventListener('click', refresh);
  refs.scan.addEventListener('click', scan);
  refs.violations.addEventListener('click', resolve);
  refs.seats.addEventListener('click', toggleSeat);
}

function switchTab(name) {
  currentTab = name;
  $$('[data-tab]', refs.tabs).forEach((el) => el.classList.toggle('active', el.dataset.tab === name));
  ['overview', 'violations', 'seats', 'users'].forEach((key) => {
    refs[key].classList.toggle('hidden', key !== name);
  });
  refresh();
}

export async function refresh() {
  if (!refs) return;
  try {
    const jobs = [api.stats(), api.violations()];
    if (currentTab === 'seats') jobs.push(api.adminSeats());
    if (currentTab === 'users') jobs.push(api.users());

    const [stats, violations, extra] = await Promise.all(jobs);
    renderOverview(stats.stats);
    renderViolations(violations.violations);
    if (currentTab === 'seats') renderSeats(extra.seats);
    if (currentTab === 'users') renderUsers(extra.users);
  } catch (error) {
    toast(error.message, 'error');
  }
}

function renderOverview(stats) {
  const cards = [
    ['总预约数', stats.total, '累计'],
    ['今日预约', stats.today, '今天'],
    ['正在学习', stats.checked_in, '签到中'],
    ['开放预警', stats.open_violations, '需关注'],
    ['取消率', `${stats.cancel_rate}%`, '占总量'],
    ['失约率', `${stats.violation_rate}%`, '超时未签到'],
  ];
  $('#statsCards').innerHTML = cards
    .map(
      ([label, value, hint]) =>
        `<div class="stat-card"><small>${label}</small><strong>${value}</strong><small>${hint}</small></div>`
    )
    .join('');

  const trend = [...(stats.by_day || [])].reverse();
  renderLine($('#trendChart'), trend, { height: 200 });
  renderRankBars($('#popularChart'), stats.popular || [], { unit: ' 次' });
  renderDonut(
    $('#slotChart'),
    (stats.by_slot || []).map((item) => ({ label: item.start_time, count: item.count })),
    { size: 170 }
  );
  renderDonut(
    $('#floorChart'),
    (stats.by_floor || []).map((item) => ({ label: `${item.floor} 楼`, count: item.count })),
    { size: 170 }
  );
  renderBars(
    $('#cancelChart'),
    [
      { label: '已完成', count: stats.total - stats.cancelled - stats.expired },
      { label: '已取消', count: stats.cancelled },
      { label: '已失效', count: stats.expired },
    ],
    { height: 170, color: '#f59e0b' }
  );
}

function renderViolations(items) {
  if (!items.length) {
    refs.violations.innerHTML = emptyState('暂无违规预警，系统运行正常');
    return;
  }
  refs.violations.innerHTML = `<div class="table-wrap"><table class="data-table">
    <thead><tr><th>用户</th><th>座位</th><th>类型</th><th>说明</th><th>时间</th><th>状态</th><th></th></tr></thead>
    <tbody>${items
      .map(
        (item) => `<tr>
          <td>${esc(item.user_name)}<small class="cell-sub">@${esc(item.username)}</small></td>
          <td>${esc(item.seat_code || '—')}</td>
          <td><span class="badge ${item.kind === 'no_show' ? 'badge-danger' : 'badge-warn'}">${
            item.kind === 'no_show' ? '超时未签到' : '超时占用'
          }</span></td>
          <td class="cell-wide">${esc(item.message)}</td>
          <td>${formatDateTime(item.created_at)}</td>
          <td>${item.status === 'open' ? '<span class="badge badge-warn">待处理</span>' : '<span class="badge badge-muted">已处理</span>'}</td>
          <td>${
            item.status === 'open'
              ? `<button type="button" class="text-btn" data-resolve="${item.id}">标记已处理</button>`
              : ''
          }</td>
        </tr>`
      )
      .join('')}</tbody></table></div>`;
}

function renderSeats(items) {
  refs.seats.innerHTML = `<div class="table-wrap"><table class="data-table">
    <thead><tr><th>编号</th><th>楼层</th><th>区域</th><th>属性</th><th>状态</th><th>操作</th></tr></thead>
    <tbody>${items
      .map(
        (seat) => `<tr>
          <td><strong>${esc(seat.code)}</strong></td>
          <td>${seat.floor} 楼</td>
          <td>${esc(seat.zone)}</td>
          <td>${seat.near_window ? '靠窗 ' : ''}${seat.power ? '电源' : ''}${!seat.near_window && !seat.power ? '—' : ''}</td>
          <td>${
            seat.status === 'available'
              ? '<span class="badge badge-ok">开放</span>'
              : '<span class="badge badge-danger">维护中</span>'
          }</td>
          <td><button type="button" class="text-btn" data-seat="${seat.id}" data-next="${
            seat.status === 'available' ? 'maintenance' : 'available'
          }">${seat.status === 'available' ? '设为维护' : '恢复开放'}</button></td>
        </tr>`
      )
      .join('')}</tbody></table></div>`;
}

function renderUsers(items) {
  refs.users.innerHTML = `<div class="table-wrap"><table class="data-table">
    <thead><tr><th>ID</th><th>账号</th><th>姓名</th><th>角色</th><th>预约数</th><th>待处理违规</th></tr></thead>
    <tbody>${items
      .map(
        (user) => `<tr>
          <td>${user.id}</td>
          <td>${esc(user.username)}</td>
          <td>${esc(user.name)}</td>
          <td><span class="badge ${user.role === 'admin' ? 'badge-ok' : 'badge-muted'}">${
            user.role === 'admin' ? '管理员' : '学生'
          }</span></td>
          <td>${user.reservation_count}</td>
          <td>${user.open_violations > 0 ? `<span class="badge badge-danger">${user.open_violations}</span>` : '0'}</td>
        </tr>`
      )
      .join('')}</tbody></table></div>`;
}

async function resolve(event) {
  const button = event.target.closest('[data-resolve]');
  if (!button) return;
  button.disabled = true;
  try {
    await api.resolveViolation(Number(button.dataset.resolve));
    toast('违规记录已处理');
    await refresh();
  } catch (error) {
    toast(error.message, 'error');
  } finally {
    button.disabled = false;
  }
}

async function toggleSeat(event) {
  const button = event.target.closest('[data-seat]');
  if (!button) return;
  button.disabled = true;
  try {
    const data = await api.setSeatStatus(Number(button.dataset.seat), button.dataset.next);
    toast(data.message);
    const seats = await api.adminSeats();
    renderSeats(seats.seats);
  } catch (error) {
    toast(error.message, 'error');
  } finally {
    button.disabled = false;
  }
}

async function scan() {
  refs.scan.disabled = true;
  try {
    const data = await api.scanViolations();
    const { expired, overstay, violations } = data.summary;
    toast(`扫描完成：失效 ${expired} 条，超时占用 ${overstay} 条，新增违规 ${violations} 条`);
    await refresh();
  } catch (error) {
    toast(error.message, 'error');
  } finally {
    refs.scan.disabled = false;
  }
}

export function onShow() {
  if (refs) refresh();
}
