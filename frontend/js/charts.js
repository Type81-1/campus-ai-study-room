/**
 * 轻量 SVG 图表：柱状 / 折线（带面积）/ 环形 / 横向条。
 *
 * 为什么自己写而不引第三方库：整个项目保持零依赖，离线答辩不需要外网 CDN，
 * 代码量可控（约 200 行）且答辩时能讲清每条指令的含义。
 * 所有图表使用 viewBox，宽度自适应容器。
 */
const PALETTE = ['#2563eb', '#16a46a', '#f59e0b', '#7c3aed', '#e55b5b', '#0891b2', '#db2777'];
const WIDTH = 600;

function empty(host, text = '暂无数据') {
  host.innerHTML = `<div class="empty">${text}</div>`;
}

function num(value) {
  const n = Number(value);
  return Number.isFinite(n) ? n : 0;
}

function short(label, max = 6) {
  const text = String(label ?? '');
  return text.length > max ? `${text.slice(0, max)}…` : text;
}

/** 柱状图：适合「近 7 日预约趋势」 */
export function renderBars(host, items, options = {}) {
  const { height = 190, valueKey = 'count', labelKey = 'day', color = PALETTE[0], unit = '' } = options;
  if (!items || !items.length) return empty(host);

  const pad = { top: 22, right: 10, bottom: 28, left: 10 };
  const innerW = WIDTH - pad.left - pad.right;
  const innerH = height - pad.top - pad.bottom;
  const max = Math.max(...items.map((item) => num(item[valueKey])), 1);
  const band = innerW / items.length;
  const barW = Math.min(46, band * 0.52);

  const parts = [];
  items.forEach((item, index) => {
    const value = num(item[valueKey]);
    const barH = Math.max(3, (value / max) * innerH);
    const x = pad.left + band * index + (band - barW) / 2;
    const y = pad.top + innerH - barH;
    parts.push(
      `<rect x="${x.toFixed(1)}" y="${y.toFixed(1)}" width="${barW.toFixed(1)}" height="${barH.toFixed(1)}" rx="6" fill="${color}" opacity="0.85"></rect>`,
      `<text x="${(x + barW / 2).toFixed(1)}" y="${(y - 6).toFixed(1)}" text-anchor="middle" class="chart-value">${value}${unit}</text>`,
      `<text x="${(x + barW / 2).toFixed(1)}" y="${height - 8}" text-anchor="middle" class="chart-label">${short(item[labelKey], 5)}</text>`
    );
  });

  host.innerHTML = `<svg viewBox="0 0 ${WIDTH} ${height}" class="chart" role="img">${parts.join('')}</svg>`;
}

/** 折线图（带面积）：适合趋势 */
export function renderLine(host, items, options = {}) {
  const { height = 190, valueKey = 'count', labelKey = 'day', color = PALETTE[0] } = options;
  if (!items || !items.length) return empty(host);

  const pad = { top: 22, right: 18, bottom: 28, left: 18 };
  const innerW = WIDTH - pad.left - pad.right;
  const innerH = height - pad.top - pad.bottom;
  const max = Math.max(...items.map((item) => num(item[valueKey])), 1);
  const step = items.length > 1 ? innerW / (items.length - 1) : 0;

  const points = items.map((item, index) => {
    const x = pad.left + step * index;
    const y = pad.top + innerH - (num(item[valueKey]) / max) * innerH;
    return { x, y, item };
  });

  const line = points.map((p) => `${p.x.toFixed(1)},${p.y.toFixed(1)}`).join(' ');
  const area = `${pad.left},${pad.top + innerH} ${line} ${(pad.left + step * (items.length - 1)).toFixed(1)},${pad.top + innerH}`;

  const grid = [0, 0.5, 1]
    .map((ratio) => {
      const y = pad.top + innerH * ratio;
      return `<line x1="${pad.left}" y1="${y}" x2="${WIDTH - pad.right}" y2="${y}" class="chart-grid"></line>`;
    })
    .join('');

  const dots = points
    .map(
      (p) =>
        `<circle cx="${p.x.toFixed(1)}" cy="${p.y.toFixed(1)}" r="3.5" fill="#fff" stroke="${color}" stroke-width="2"></circle>` +
        `<text x="${p.x.toFixed(1)}" y="${(p.y - 9).toFixed(1)}" text-anchor="middle" class="chart-value">${num(p.item[valueKey])}</text>`
    )
    .join('');

  const labels = points
    .map(
      (p) =>
        `<text x="${p.x.toFixed(1)}" y="${height - 8}" text-anchor="middle" class="chart-label">${short(p.item[labelKey], 5)}</text>`
    )
    .join('');

  host.innerHTML = `<svg viewBox="0 0 ${WIDTH} ${height}" class="chart" role="img">
    <defs>
      <linearGradient id="areaFill" x1="0" y1="0" x2="0" y2="1">
        <stop offset="0%" stop-color="${color}" stop-opacity="0.28"></stop>
        <stop offset="100%" stop-color="${color}" stop-opacity="0.02"></stop>
      </linearGradient>
    </defs>
    ${grid}
    <polygon points="${area}" fill="url(#areaFill)"></polygon>
    <polyline points="${line}" fill="none" stroke="${color}" stroke-width="2.5" stroke-linejoin="round" stroke-linecap="round"></polyline>
    ${dots}${labels}
  </svg>`;
}

/** 环形图：适合占比（时段分布、楼层分布） */
export function renderDonut(host, items, options = {}) {
  const { size = 180, valueKey = 'count', labelKey = 'label', thickness = 22 } = options;
  const total = (items || []).reduce((sum, item) => sum + num(item[valueKey]), 0);
  if (!items || !items.length || total === 0) return empty(host);

  const radius = size / 2 - thickness / 2 - 2;
  const circumference = 2 * Math.PI * radius;
  const center = size / 2;
  let offset = 0;

  const arcs = items
    .map((item, index) => {
      const value = num(item[valueKey]);
      const length = (value / total) * circumference;
      const circle = `<circle cx="${center}" cy="${center}" r="${radius}"
        fill="none" stroke="${PALETTE[index % PALETTE.length]}" stroke-width="${thickness}"
        stroke-dasharray="${length.toFixed(2)} ${(circumference - length).toFixed(2)}"
        stroke-dashoffset="${(-offset).toFixed(2)}"
        transform="rotate(-90 ${center} ${center})" stroke-linecap="butt"></circle>`;
      offset += length;
      return circle;
    })
    .join('');

  const legend = items
    .map((item, index) => {
      const value = num(item[valueKey]);
      const percent = ((value / total) * 100).toFixed(0);
      return `<li><i style="background:${PALETTE[index % PALETTE.length]}"></i>
        <span>${short(item[labelKey], 8)}</span><strong>${value}（${percent}%）</strong></li>`;
    })
    .join('');

  host.innerHTML = `<div class="donut">
    <svg viewBox="0 0 ${size} ${size}" class="chart donut-svg" role="img">
      <circle cx="${center}" cy="${center}" r="${radius}" fill="none" stroke="#eef2f7" stroke-width="${thickness}"></circle>
      ${arcs}
      <text x="${center}" y="${center - 2}" text-anchor="middle" class="chart-total">${total}</text>
      <text x="${center}" y="${center + 16}" text-anchor="middle" class="chart-label">总计</text>
    </svg>
    <ul class="chart-legend">${legend}</ul>
  </div>`;
}

/** 横向条：适合排行（热门座位） */
export function renderRankBars(host, items, options = {}) {
  const { valueKey = 'count', labelKey = 'code', color = PALETTE[1], unit = '次' } = options;
  if (!items || !items.length) return empty(host);

  const max = Math.max(...items.map((item) => num(item[valueKey])), 1);
  host.innerHTML = `<div class="rank-list">${items
    .map((item) => {
      const value = num(item[valueKey]);
      const width = Math.max(6, (value / max) * 100);
      return `<div class="rank-row">
        <span class="rank-label">${short(item[labelKey], 8)}</span>
        <div class="rank-track"><div class="rank-fill" style="width:${width.toFixed(1)}%;background:${color}"></div></div>
        <strong>${value}${unit}</strong>
      </div>`;
    })
    .join('')}</div>`;
}
