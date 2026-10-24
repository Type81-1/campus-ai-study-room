# 前端目录

原生 HTML / CSS / ES Module，**零第三方依赖**（图表也是自研 SVG），由后端 `backend/web.py` 直接托管，不需要构建步骤。

## 结构

```text
frontend/
├─ index.html          页面骨架（登录页 + 四个功能页 + 座位弹窗）
├─ styles.css          全部样式（含图表、表格、页签、徽章、实时状态、响应式）
├─ favicon.svg         站点图标
├─ js/
│  ├─ main.js          入口：会话恢复、页面切换、全局事件、实时通道启停
│  ├─ api.js           请求封装：Bearer 令牌、统一错误、401 处理
│  ├─ realtime.js      SSE 订阅：连接状态、事件分发、断线重连
│  ├─ store.js         轻量状态与事件（当前用户、预约选择）
│  ├─ ui.js            DOM 工具、提示、状态徽章、时段选项
│  ├─ charts.js        SVG 图表：柱状 / 折线（带面积）/ 环形 / 排行
│  └─ pages/
│     ├─ booking.js    预约座位：时段筛选、座位网格、预约弹窗
│     ├─ my.js         我的预约：签到 / 结束 / 取消
│     ├─ recommend.js  智能推荐：热度条 + 分数条 + 可解释理由
│     └─ admin.js      管理看板：概览 / 违规 / 座位 / 用户
└─ tests/
   ├─ ui-smoke.mjs     jsdom 冒烟：真实页面 + 真实模块，25 项检查
   ├─ ui-e2e.mjs       Playwright 真实浏览器：22 项检查 + 截图像素基线
   └─ screenshots/     运行产物（baseline/ 下是基线，需随仓库提交）
```

## 约定

- **身份**：登录后令牌存 `localStorage`（键 `studyRoomToken`），`api.js` 统一加 `Authorization: Bearer`；收到 401 时清令牌并广播 `auth:expired`，由 `main.js` 回到登录页。
- **页面契约**：每个 `pages/*.js` 导出 `init()` 与 `refresh()`；`main.js` 在启动时统一 `init`，切换页签时调用 `refresh`。
- **跨页刷新**：写操作后 `window.dispatchEvent(new CustomEvent('data:changed', { detail: { page } }))`，通知相关页面刷新。
- **实时刷新**：`realtime.js` 订阅 `/api/events`，收到事件后由各页面自己决定是否刷新（`page-*` 不可见时跳过），并做 500~700ms 去抖。
- **图表**：`charts.js` 只接收数据数组，输出 SVG 字符串，颜色取自内置调色板，无需联网加载图表库。

## 本地调试

```powershell
python backend/server.py     # 启动后端（含静态托管）
python scripts/seed_demo.py  # 可选：灌演示数据
```

访问 <http://127.0.0.1:8000>。浏览器需支持 ES Module 与 `EventSource`（Chrome 61+ / Edge 79+ / Firefox 60+）。

## 前端测试

```powershell
cd frontend/tests
npm install

# 1) jsdom 冒烟：验证逻辑与选择器
BASE_URL=http://127.0.0.1:8000 node ui-smoke.mjs

# 2) 真实浏览器：验证渲染、布局、截图基线（用本机 Chrome/Edge，不下载 Chromium）
BASE_URL=http://127.0.0.1:8000 node ui-e2e.mjs
BASE_URL=http://127.0.0.1:8000 node ui-e2e.mjs --update   # 改版后重建基线
```

截图基线默认允许 2% 像素差异（`PW_DIFF_THRESHOLD` 可调），超出会输出 `*.diff.png` 便于定位。
数据驱动的数字在截图前会被替换为占位符，日期文案固定为 `TODAY`，避免基线随演示数据漂移。
