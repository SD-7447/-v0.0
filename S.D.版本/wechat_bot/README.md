# 微信 ClawBot 传话筒通道 — 安装指南

> 目标：微信里给 ClawBot 发一张单据图片 → OpenClaw **不做任何 AI 分析**，直接 HTTP POST 到本地 WebApp → WebApp 识别入账 → 回复文本原样回显到微信。

```
微信  ──图片──▶  ClawBot 插件（微信官方）
                    │
                    ▼
              OpenClaw Gateway（本机常驻，端口 18789）
                    │  命中 sd-finance-relay 技能（本目录 openclaw-skill/）
                    ▼
              node forward_to_webapp.js <图片> [发送者]
                    │  POST /api/bot/upload
                    ▼
              本地 WebApp（默认 http://127.0.0.1:8000）识别 + 入账
                    │  {status, reply, record_id}
                    ▼
              reply 文本回显到微信 ✅/⚠️/🔁/❌
```

---

## 一、前置条件

| 项 | 要求 | 说明 |
|---|---|---|
| 微信版本 | iOS ≥ 8.0.70（安卓以应用内是否有插件入口为准） | 微信「我 → 设置 → 插件」里能看到 ClawBot 入口才可绑定 |
| Node.js | ≥ 18 | 转发脚本零依赖，只用内置 `fetch`；`node -v` 确认 |
| OpenClaw | 已安装并能运行 | 未装则先按 OpenClaw 官方文档安装 |
| WebApp | S.D.版本 v0.3+，已启动 | `python -m uvicorn app.main:app --port 8000` |

> ⚠️ ClawBot 目前处于灰度阶段，部分账号可能看不到插件入口——这不是本项目能解决的问题，只能等待放量或换号。

## 二、安装步骤

### 1. 安装微信 ClawBot 插件（二选一）

```bash
npx -y @tencent-weixin/openclaw-weixin-cli@latest install
# 或
openclaw plugins install @tencent-weixin/openclaw-weixin
```

安装过程中会弹出微信**扫码绑定**——用装了 ≥ 8.0.70 版本微信的手机扫码完成绑定。

### 2. 保持 Gateway 常驻

```bash
openclaw gateway
```

Gateway 默认配置目录为 `~/.openclaw`，本地监听 18789 端口。微信消息经由该 Gateway 进出。

### 3. 装入传话筒技能

把本目录的 `openclaw-skill/`（即 `sd-finance-relay`）复制到 OpenClaw 的技能目录，例如：

```
~/.openclaw/skills/sd-finance-relay/SKILL.md
```

并把 `forward_to_webapp.js` 放到技能内指定的路径（SKILL.md 内写的是相对引用，直接整目录同级放置即可）。重启 Gateway 使技能生效。

### 4. 配置鉴权令牌（推荐，防局域网内误传/伪造）

1. 打开 WebApp 管理后台（`http://127.0.0.1:8000/admin`），在配置区填入 **微信 Bot 令牌（BOT_TOKEN）** 并保存——自己编一个随机长字符串即可，如 `openssl rand -hex 16`。
2. 在运行 Gateway 的机器上设置环境变量，让转发脚本带上同一个令牌：

```bash
# macOS / Linux
export SD_BOT_TOKEN="你的令牌"
# Windows（PowerShell）
$env:SD_BOT_TOKEN = "你的令牌"
# Windows（cmd）
set SD_BOT_TOKEN=你的令牌
```

> 不配 BOT_TOKEN 也能用（接口会放行并记日志），但任何能访问到 8000 端口的程序都能往里灌数据，**强烈建议配置**。

如果 WebApp 不在本机（例如部署到云服务器），还需设置 `SD_WEBAPP_URL`，如 `https://your-domain.com`；云端访问本机则需要 ngrok / frp 等内网穿透。

### 5. 本地自测（不发微信，直接打接口）

```bash
cd wechat_bot
node test_local.js            # 无令牌场景
# 或带令牌
SD_BOT_TOKEN=你的令牌 node test_local.js
```

期望输出一行 `✅ 已入账 …` 开头的回复文本。若返回 `403`，说明令牌不匹配；`422` 说明文件类型不被接受。

### 6. 微信实测

在微信里给 ClawBot 发一张单据图片，几秒内应收到识别结果回显（✅ 成功 / ⚠️ 部分字段缺失 / 🔁 疑似重复 / ❌ 失败原因）。回到 WebApp 首页，明细表「来源」列应显示 **微信** 标记。

## 三、排错速查

| 现象 | 原因 | 处理 |
|---|---|---|
| `npx ... install` 报错 | 网络或 npm 源问题 | 换网络 / `npm config set registry https://registry.npmmirror.com` 后重试 |
| 微信里找不到 ClawBot 插件入口 | 微信版本过低或账号不在灰度范围 | 升级微信至 ≥ 8.0.70；仍无入口只能等放量 |
| 扫码后绑定失败 | Gateway 未运行或配置目录损坏 | 确认 `openclaw gateway` 在跑；必要时备份后重置 `~/.openclaw` |
| 微信发图无回显 | 技能未生效 / 脚本路径不对 / WebApp 没启动 | 重启 Gateway；手动跑一次 `node forward_to_webapp.js <某张图>` 看报错 |
| 微信回显 ❌ 401/403 | 两端 BOT_TOKEN 不一致 | 核对管理后台保存的令牌与 `SD_BOT_TOKEN` 环境变量 |

## 四、网络打通对照表

| WebApp 位置 | Gateway 位置 | 做法 |
|---|---|---|
| 本机 | 本机 | 默认即可（`http://127.0.0.1:8000`） |
| 本机 | 云服务器 | 需内网穿透（ngrok / frp），`SD_WEBAPP_URL` 指向穿透地址 |
| 云服务器 | 云服务器（同机） | 默认即可 |
| 云服务器 | 本机 | `SD_WEBAPP_URL` 指向云服务器公网地址，注意开放端口与 HTTPS |

## 五、诚实声明

微信侧链路（扫码绑定、消息收发）依赖微信客户端与 OpenClaw Gateway，**无法在本仓库内做端到端自动化验证**。`node test_local.js` 能覆盖「脚本 → WebApp → 入账 → 回复文本」这一整段，微信侧的最后一步需要用户扫码实测。遇到问题时，把 `test_local.js` 的输出和 Gateway 日志一起发回来即可定位。
