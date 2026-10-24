/** 预约座位页：时段筛选、座位网格、预约弹窗。 */
import { api } from '../api.js';
import { $, esc, fillTimeSelect, loading, toast, todayISO } from '../ui.js';
import { state } from '../store.js';
import { subscribe } from '../realtime.js';

let refs = null;

export function init() {
  refs = {
    date: $('#bookingDate'),
    start: $('#startTime'),
    end: $('#endTime'),
    grid: $('#seatGrid'),
    count: $('#availableCount'),
    refresh: $('#refreshSeats'),
    modal: $('#seatModal'),
    title: $('#modalSeatTitle'),
    meta: $('#modalSeatMeta'),
    window: $('#modalWindow'),
    power: $('#modalPower'),
    confirm: $('#confirmBooking'),
  };

  refs.date.value = todayISO();
  refs.date.min = todayISO();
  fillTimeSelect(refs.start, { value: '09:00' });
  fillTimeSelect(refs.end, { value: '11:00', from: 2 });
  state.booking = { date: refs.date.value, start: refs.start.value, end: refs.end.value };

  refs.refresh.addEventListener('click', refresh);
  refs.date.addEventListener('change', refresh);
  refs.start.addEventListener('change', refresh);
  refs.end.addEventListener('change', refresh);
  refs.confirm.addEventListener('click', submit);

  refs.grid.addEventListener('click', (event) => {
    const card = event.target.closest('.seat-card');
    if (card && !card.disabled) openModal(Number(card.dataset.seat));
  });

  refs.modal.addEventListener('click', (event) => {
    if (event.target.matches('[data-close], .modal')) refs.modal.classList.add('hidden');
  });

  // 别人下单 / 取消 / 座位维护后，当前页自动刷新
  let timer = null;
  subscribe(() => {
    if ($('#page-booking')?.classList.contains('hidden')) return;
    clearTimeout(timer);
    timer = setTimeout(refresh, 500);
  });
}

export async function refresh() {
  if (!refs) return;
  const { date, start, end } = readRange();
  if (!date) return toast('请先选择日期');
  if (end <= start) return toast('结束时间必须晚于开始时间');

  refs.grid.innerHTML = loading(4);
  try {
    const data = await api.seats(date, start, end);
    state.seats = data.seats;
    state.booking = { date, start, end };
    renderSeats(data.seats);
  } catch (error) {
    refs.grid.innerHTML = '';
    toast(error.message, 'error');
  }
}

function readRange() {
  return { date: refs.date.value, start: refs.start.value, end: refs.end.value };
}

function renderSeats(seats) {
  const available = seats.filter((seat) => seat.available).length;
  refs.count.textContent = String(available);

  if (!seats.length) {
    refs.grid.innerHTML = '<div class="empty">暂无座位数据</div>';
    return;
  }

  refs.grid.innerHTML = seats
    .map((seat) => {
      const tags = [
        seat.near_window ? '<span class="tag">靠窗</span>' : '',
        seat.power ? '<span class="tag">电源</span>' : '',
      ].join('');
      const cls = seat.available ? 'available' : 'busy';
      return `<button type="button" class="seat-card ${cls}" ${seat.available ? '' : 'disabled'} data-seat="${seat.id}">
        <span class="seat-status">${esc(seat.status_label)}</span>
        <span class="seat-code">${esc(seat.code)}</span>
        <span class="seat-sub">${esc(seat.zone)} · ${seat.floor} 楼</span>
        <span class="seat-tags">${tags}</span>
      </button>`;
    })
    .join('');
}

function openModal(seatId) {
  const seat = state.seats.find((item) => item.id === seatId);
  if (!seat) return;
  state.selectedSeat = seat;
  refs.title.textContent = seat.code;
  refs.meta.textContent = `${seat.floor} 楼 · ${seat.zone} · ${state.booking.date} ${state.booking.start}—${state.booking.end}`;
  refs.window.textContent = seat.near_window ? '靠窗座位' : '室内座位';
  refs.power.textContent = seat.power ? '提供电源' : '无电源';
  refs.modal.classList.remove('hidden');
}

async function submit() {
  const seat = state.selectedSeat;
  if (!seat) return;
  refs.confirm.disabled = true;
  try {
    await api.createReservation({
      seat_id: seat.id,
      reservation_date: state.booking.date,
      start_time: state.booking.start,
      end_time: state.booking.end,
    });
    refs.modal.classList.add('hidden');
    toast('预约成功，记得按时签到');
    await refresh();
    window.dispatchEvent(new CustomEvent('data:changed', { detail: { page: 'mine' } }));
  } catch (error) {
    toast(error.message, 'error');
  } finally {
    refs.confirm.disabled = false;
  }
}
