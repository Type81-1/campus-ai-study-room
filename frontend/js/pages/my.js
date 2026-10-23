/** 我的预约页：列表 + 签到 / 结束 / 取消。 */
import { api } from '../api.js';
import { $, esc, formatDate, loading, statusBadge, toast, emptyState } from '../ui.js';

let refs = null;

export function init() {
  refs = { list: $('#reservationList'), refresh: $('#mineRefresh') };
  refs.refresh.addEventListener('click', refresh);
  refs.list.addEventListener('click', onClick);
}

export async function refresh() {
  if (!refs) return;
  refs.list.innerHTML = loading(3);
  try {
    const data = await api.myReservations();
    render(data.reservations);
  } catch (error) {
    refs.list.innerHTML = emptyState(error.message);
  }
}

function render(items) {
  if (!items.length) {
    refs.list.innerHTML = emptyState('还没有预约记录，去「预约座位」挑一个吧');
    return;
  }
  refs.list.innerHTML = items
    .map((item) => {
      const actions = [];
      if (item.status === 'booked') {
        actions.push(`<button type="button" class="text-btn" data-action="checkin" data-id="${item.id}">签到核销</button>`);
        actions.push(`<button type="button" class="text-btn danger" data-action="cancel" data-id="${item.id}">取消</button>`);
      }
      if (item.status === 'checked_in') {
        actions.push(`<button type="button" class="text-btn" data-action="checkout" data-id="${item.id}">结束自习</button>`);
      }
      const hint =
        item.status === 'booked' && item.checkin_window
          ? `<small class="hint">可签到时段 ${esc(item.checkin_window)}</small>`
          : '';
      return `<article class="reservation-item">
        <div class="reservation-main">
          <div class="reservation-icon">${esc(String(item.seat_code || '').split('-').pop())}</div>
          <div>
            <strong>${esc(item.seat_code)} ${statusBadge(item.status)}</strong>
            <small>${formatDate(item.reservation_date)} · ${esc(item.start_time)}—${esc(item.end_time)} · ${esc(item.zone)}</small>
            ${hint}
          </div>
        </div>
        <div class="reservation-actions">${actions.join('')}</div>
      </article>`;
    })
    .join('');
}

async function onClick(event) {
  const button = event.target.closest('[data-action]');
  if (!button) return;
  const id = Number(button.dataset.id);
  const action = button.dataset.action;
  button.disabled = true;
  try {
    if (action === 'checkin') {
      await api.checkin(id);
      toast('签到成功，祝学习专注');
    } else if (action === 'checkout') {
      await api.checkout(id);
      toast('本次自习已结束');
    } else if (action === 'cancel') {
      if (!window.confirm('确定取消这条预约吗？')) return;
      await api.cancelReservation(id);
      toast('预约已取消');
    }
    await refresh();
    window.dispatchEvent(new CustomEvent('data:changed', { detail: { page: 'booking' } }));
  } catch (error) {
    toast(error.message, 'error');
  } finally {
    button.disabled = false;
  }
}
