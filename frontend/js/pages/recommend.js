/** 智能推荐页：按偏好打分排序，展示可解释理由。 */
import { api } from '../api.js';
import { $, esc, fillTimeSelect, loading, toast, todayISO, emptyState } from '../ui.js';

let refs = null;

export function init() {
  refs = {
    date: $('#recommendDate'),
    start: $('#recommendStart'),
    end: $('#recommendEnd'),
    list: $('#recommendList'),
    action: $('#loadRecommendations'),
  };
  refs.date.value = todayISO();
  refs.date.min = todayISO();
  fillTimeSelect(refs.start, { value: '09:00' });
  fillTimeSelect(refs.end, { value: '11:00', from: 2 });
  refs.action.addEventListener('click', refresh);
  refs.list.addEventListener('click', onBook);
}

export async function refresh() {
  if (!refs) return;
  const date = refs.date.value;
  const start = refs.start.value;
  const end = refs.end.value;
  if (!date) return toast('请先选择日期');
  if (end <= start) return toast('结束时间必须晚于开始时间');

  refs.list.innerHTML = loading(3);
  try {
    const data = await api.recommendations(date, start, end);
    render(data.recommendations, { date, start, end });
  } catch (error) {
    refs.list.innerHTML = emptyState(error.message);
  }
}

function render(items, slot) {
  if (!items.length) {
    refs.list.innerHTML = emptyState('当前时段没有空闲座位，换个时间试试');
    return;
  }
  const maxScore = Math.max(...items.map((item) => item.score), 1);
  refs.list.innerHTML = items
    .map((item) => {
      const width = Math.max(12, (item.score / maxScore) * 100);
      return `<article class="recommend-item">
        <div class="score">${item.score}</div>
        <div class="details">
          <strong>${esc(item.code)}</strong>
          <p>${item.floor} 楼 · ${esc(item.zone)} · ${esc(item.reason)}</p>
          <div class="score-track"><div class="score-fill" style="width:${width.toFixed(1)}%"></div></div>
        </div>
        <button type="button" class="primary" data-seat="${item.id}" data-date="${esc(slot.date)}"
          data-start="${esc(slot.start)}" data-end="${esc(slot.end)}">预约</button>
      </article>`;
    })
    .join('');
}

async function onBook(event) {
  const button = event.target.closest('[data-seat]');
  if (!button) return;
  button.disabled = true;
  try {
    await api.createReservation({
      seat_id: Number(button.dataset.seat),
      reservation_date: button.dataset.date,
      start_time: button.dataset.start,
      end_time: button.dataset.end,
    });
    toast('推荐座位预约成功');
    await refresh();
    window.dispatchEvent(new CustomEvent('data:changed', { detail: { page: 'mine' } }));
  } catch (error) {
    toast(error.message, 'error');
  } finally {
    button.disabled = false;
  }
}
