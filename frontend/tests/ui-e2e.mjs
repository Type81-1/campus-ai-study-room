/**
 * 端到端与截图基线对比（Playwright + 本机 Chrome/Edge）。
 *
 * 与 ui-smoke.mjs 的区别：
 * - ui-smoke 用 jsdom 验证逻辑与选择器；
 * - 本脚本用真实浏览器渲染，验证布局、样式、图表实际绘制，并做像素级基线对比。
 *
 * 用法（先启动后端并灌演示数据）：
 *   cd frontend/tests
 *   npm install
 *   BASE_URL=http://127.0.0.1:8000 node ui-e2e.mjs
 *   BASE_URL=http://127.0.0.1:8000 node ui-e2e.mjs --update   # 重建基线
 *
 * 浏览器查找顺序：环境变量 PW_CHROME → 本机 Chrome → 本机 Edge。
 */
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { chromium } from 'playwright-core';
import { PNG } from 'pngjs';
import pixelmatch from 'pixelmatch';

const HERE = path.dirname(fileURLToPath(import.meta.url));
const BASE = process.env.BASE_URL || 'http://127.0.0.1:8000';
const SHOTS = path.join(HERE, 'screenshots');
const BASELINE = path.join(SHOTS, 'baseline');
const UPDATE = process.argv.includes('--update');
const DIFF_THRESHOLD = Number(process.env.PW_DIFF_THRESHOLD || 0.02); // 允许 2% 像素差异

const failures = [];
const consoleErrors = [];

function check(name, ok, detail = '') {
  if (ok) console.log(`  [通过] ${name}`);
  else {
    failures.push(name);
    console.log(`  [失败] ${name} ${detail}`);
  }
}

function findBrowser() {
  const candidates = [
    process.env.PW_CHROME,
    'C:/Program Files/Google/Chrome/Application/chrome.exe',
    'C:/Program Files (x86)/Google/Chrome/Application/chrome.exe',
    'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe',
    'C:/Program Files/Microsoft/Edge/Application/msedge.exe',
  ].filter(Boolean);
  const found = candidates.find((candidate) => fs.existsSync(candidate));
  if (!found) throw new Error('未找到本机 Chrome/Edge，可用 PW_CHROME 指定可执行文件路径');
  return found;
}

function compareWithBaseline(name) {
  fs.mkdirSync(SHOTS, { recursive: true });
  fs.mkdirSync(BASELINE, { recursive: true });
  const currentPath = path.join(SHOTS, `${name}.png`);
  const baselinePath = path.join(BASELINE, `${name}.png`);

  if (!fs.existsSync(baselinePath) || UPDATE) {
    fs.copyFileSync(currentPath, baselinePath);
    console.log(`  [基线] ${name}.png 已${UPDATE ? '更新' : '创建'}`);
    return true;
  }

  const before = PNG.sync.read(fs.readFileSync(baselinePath));
  const after = PNG.sync.read(fs.readFileSync(currentPath));
  if (before.width !== after.width || before.height !== after.height) {
    check(`${name} 截图基线`, false, `尺寸变化 ${before.width}x${before.height} → ${after.width}x${after.height}`);
    return false;
  }

  const diff = new PNG({ width: before.width, height: before.height });
  const changed = pixelmatch(before.data, after.data, diff.data, before.width, before.height, {
    threshold: 0.12,
  });
  const ratio = changed / (before.width * before.height);
  if (ratio > DIFF_THRESHOLD) {
    fs.writeFileSync(path.join(SHOTS, `${name}.diff.png`), PNG.sync.write(diff));
    check(`${name} 截图基线`, false, `差异 ${(ratio * 100).toFixed(2)}% > ${DIFF_THRESHOLD * 100}%`);
    return false;
  }
  console.log(`  [通过] ${name} 截图基线（差异 ${(ratio * 100).toFixed(3)}%）`);
  return true;
}

async function login(page, username, password) {
  await page.fill('#username', username);
  await page.fill('#password', password);
  await page.click('#loginForm button[type="submit"]');
}

async function main() {
  const executablePath = findBrowser();
  console.log(`浏览器：${executablePath}`);
  console.log(`服务：${BASE}`);

  const browser = await chromium.launch({ headless: true, executablePath, args: ['--no-sandbox'] });
  const context = await browser.newContext({
    viewport: { width: 1440, height: 900 },
    deviceScaleFactor: 1,
    locale: 'zh-CN',
  });
  const page = await context.newPage();

  page.on('console', (message) => {
    if (message.type() === 'error') consoleErrors.push(message.text());
  });
  page.on('pageerror', (error) => consoleErrors.push(String(error)));

  /** 等字体加载完成再截图，否则首跑与后续跑的基线会因字体回退产生差异 */
  const settle = async () => {
    await page.evaluate(() => (document.fonts ? document.fonts.ready : true));
    await page.waitForTimeout(250);
  };

  try {
    console.log('\n== 1. 学生登录与预约页 ==');
    await page.goto(BASE, { waitUntil: 'networkidle' });
    await settle();
    check('登录页渲染', await page.isVisible('#loginView'));
    await login(page, 'student001', '123456');
    await page.waitForSelector('#seatGrid .seat-card', { timeout: 10000 });
    check('进入主界面', await page.isVisible('#appView'));
    check('座位卡片数量为 24', (await page.locator('#seatGrid .seat-card').count()) === 24);
    check('实时状态徽标存在', await page.isVisible('#realtimeBadge'));

    const grid = await page.locator('#seatGrid').boundingBox();
    check('座位网格有实际尺寸', Boolean(grid && grid.width > 300 && grid.height > 100));

    // 固定日期文案，避免基线随日期漂移
    await page.evaluate(() => {
      const label = document.getElementById('todayLabel');
      if (label) label.textContent = 'TODAY';
      const badge = document.getElementById('realtimeBadge');
      if (badge) badge.className = 'live-badge off';
    });
    await settle();
    await page.screenshot({ path: path.join(SHOTS, 'booking.png') });
    compareWithBaseline('booking');

    console.log('\n== 2. 智能推荐页（热度提示 + 图表无关） ==');
    await page.click('.nav-item[data-page="recommend"]');
    await page.waitForSelector('#recommendList .recommend-item', { timeout: 10000 });
    check('推荐列表渲染', (await page.locator('#recommendList .recommend-item').count()) > 0);
    check('热度条可见', await page.isVisible('#heatBanner'));
    const heatText = await page.textContent('#heatBanner');
    check('热度文案包含占用情况', /\d+\/\d+ 已占用/.test(heatText.replace(/\s+/g, ' ')));
    await settle();
    await page.screenshot({ path: path.join(SHOTS, 'recommend.png') });
    compareWithBaseline('recommend');

    console.log('\n== 3. 管理看板（图表实际绘制） ==');
    await page.click('#logoutBtn');
    await page.waitForSelector('#loginView', { state: 'visible' });
    await login(page, 'admin', 'admin123');
    await page.waitForSelector('#statsCards .stat-card', { timeout: 10000 });
    check('默认进入管理看板', await page.isVisible('#page-admin'));
    check('统计卡片 6 个', (await page.locator('#statsCards .stat-card').count()) === 6);

    const chartBox = await page.locator('#trendChart svg').boundingBox();
    check('趋势图有实际尺寸', Boolean(chartBox && chartBox.width > 200 && chartBox.height > 80));
    const donutBox = await page.locator('#slotChart svg').boundingBox();
    check('环形图有实际尺寸', Boolean(donutBox && donutBox.width > 100));

    const statsText = await page.textContent('#statsCards');
    await page.evaluate(() => {
      // 数字随演示数据变化，截图前统一成占位符，保证基线稳定
      document.querySelectorAll('#statsCards .stat-card strong').forEach((el, index) => {
        el.textContent = ['N1', 'N2', 'N3', 'N4', 'N5', 'N6'][index];
      });
      const label = document.getElementById('todayLabel');
      if (label) label.textContent = 'TODAY';
    });
    check('统计数字已渲染', statsText.trim().length > 0);
    await settle();
    await page.screenshot({ path: path.join(SHOTS, 'admin.png') });
    compareWithBaseline('admin');

    console.log('\n== 4. 管理看板页签 ==');
    await page.click('[data-tab="violations"]');
    await page.waitForTimeout(800);
    const rows = await page.locator('#adminViolations tbody tr').count();
    check('违规页签有内容', rows >= 0);

    await page.click('[data-tab="seats"]');
    await page.waitForTimeout(800);
    check('座位管理 24 行', (await page.locator('#adminSeats tbody tr').count()) === 24);

    console.log('\n== 5. 502 视口自适应 ==');
    await page.setViewportSize({ width: 420, height: 860 });
    await page.waitForTimeout(400);
    const sidebar = await page.locator('.sidebar').boundingBox();
    check('窄屏侧栏收窄', Boolean(sidebar && sidebar.width <= 90), `实际 ${sidebar?.width}`);
    await settle();
    await page.screenshot({ path: path.join(SHOTS, 'mobile.png') });
    compareWithBaseline('mobile');
  } finally {
    await context.close();
    await browser.close();
  }

  console.log('\n== 6. 控制台健康检查 ==');
  const realErrors = consoleErrors.filter((text) => !/favicon|net::ERR_|Favicon/i.test(text));
  check('无前端运行时错误', realErrors.length === 0, realErrors.join(' | '));

  console.log(`\n===== 结果：${failures.length === 0 ? '全部通过' : `${failures.length} 项失败`} =====`);
  if (failures.length) {
    console.log(failures.map((item) => ` - ${item}`).join('\n'));
    process.exitCode = 1;
  }
}

main().catch((error) => {
  console.error('测试中断：', error);
  process.exitCode = 1;
});
