# 前端目录

原生 HTML / CSS / ES Module，**零第三方依赖**（图表也是自研 SVG），由后端 `backend/web.py` 直接托管，不需要构建步骤。

## 结构

```text
frontend/
├─ index.html          页面骨架（登录页 + 四个功能页 + 座位弹窗）
├─ styles.css          全部样式（含 v2.1 新增的图表、表格、页签、徽章）
└─ js/
   ├─ main.js          入口：会话恢复、页面切换、全局事件
   ├─ api.js           请求封装：Bearer 令牌、统一错误、401 处理
   ├─ store.js         轻量状态与事件（当前用户、预约选择）
   ├─ ui.js            DOM 工具、提示、状态徽章、时段选项
   ├─ charts.js        SVG 图表：柱状 / 折线（带面积）/ 环形 / 排行
   └─ pages/
      ├─ booking.js    预约座位：时段筛选、座位网格、预约弹窗
      ├─ my.js         我的预约：签到 / 结束 / 取消
      ├─ recommend.js  智能推荐：分数条 + 可解释理由
      └─ admin.js      管理看板：概览 / 违规 / 座位 / 用户
```

## 约定

- **身份**：登录后令牌存 `localStorage`（键 `studyRoomToken`），`api.js` 统一加 `Authorization: Bearer`；收到 401 时清令牌并广播 `auth:expired`，由 `main.js` 回到登录页。
- **页面契约**：每个 `pages/*.js` 导出 `init()` 与 `refresh()`；`main.js` 在启动时统一 `init`，切换页签时调用 `refresh`。
- **跨页刷新**：写操作后 `window.dispatchEvent(new CustomEvent('data:changed', { detail: { page } }))`，通知相关页面刷新。
- **图表**：`charts.js` 只接收数据数组，输出 SVG 字符串，颜色取自内置调色板，无需联网加载图表库。

## 本地调试

直接启动后端即可：`python backend/server.py`，访问 <http://127.0.0.1:8000>。
浏览器需支持 ES Module（Chrome 61+ / Edge 79+ / Firefox 60+）。
