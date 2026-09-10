# AI 中小微企业智能财务系统 · Phase 1（S.D.版本 v0.4）

> 依据《企划书》（基础方针）与 2026-09-07 会议《Phase 1 开发计划》（落地方案）实现。
> 一句话目标：**做出可用的「壳子 + 全链路」——把票据照片变成三大报表**。
> v0.4：UI 重构（侧边栏五页 SPA · iOS 弹簧动效 · 扁平 SVG 图标）+ 微信连接链路自检向导。

## v0.4 新增

- **UI 重构**：单页应用 + 固定侧边栏（首页/明细/报表/连接/设置），大标题层级，hairline 分隔；页面切换为方向感非线性过渡（推入/推回 380ms 弹簧曲线），弹窗过冲回弹，列表逐项 stagger 进入；图标全部重绘为 1.6px 描边扁平 SVG（不再使用 emoji 功能图标）；深色（默认）/暖纸双主题
- **微信连接链路重构**：启动时自动调用 `GET /api/bot/status` 自检（Node 环境 → OpenClaw Gateway 端口探活 → BOT_TOKEN 配对三步）；未连接自动弹出分步连接向导（含扫码绑定指引与向导内直接保存令牌），每 3 秒轮询，**检测到连接成功后展示成功态并自动回收弹窗**；「暂不连接」可跳过（本会话内不再弹出）；侧边栏常驻连接状态灯
- **连接自检接口**：`GET /api/bot/status`（分步状态 + 微信入账统计）、`GET /api/bot/ping`（令牌回环自检，不产生入账记录）
- **设置页并入主界面**：原管理后台（密钥/检测/用量/日志/危险操作）成为 SPA 一页；旧 `/admin` 页面保留兼容

## v0.3 新增

- **微信上传通道**：`POST /api/bot/upload`（`app/routers/bot.py`），收字节流 + `X-Bot-Token`/`X-User`/`X-File-Name` 头，令牌鉴权（未配置则放行并记日志），返回带 ✅/⚠️/🔁/❌ 图标的 `reply` 文本直接回显微信
- **来源标记**：暂存记录新增 `source` 字段（web/wechat，老库自动迁移），明细表「来源」列区分微信/网页上传
- **传话筒套件**（`wechat_bot/`）：OpenClaw 零依赖转发脚本 `forward_to_webapp.js`、`sd-finance-relay` 技能（明确禁止 AI 侧分析图片）、本地自测 `test_local.js`、完整安装指南 `README.md`（安装 → 扫码 → 配令牌 → 自测 → 排错表）
- **管理后台**：新增「微信 Bot 令牌（BOT_TOKEN）」配置项与上传接口地址展示

## v0.2 新增

- **管理后台**（`/admin`）：API KEY 在线更换（免重启）、Token/密钥连通性检测（401/403/429 分类提示 + 延迟）、Token 用量台账（按端口聚合 + 最近调用明细）、系统状态、操作日志、危险操作二次确认
- **简版复式记账内核**（`app/ledger.py`）：每张票据生成借贷分录（价税分离、现金/挂账自动区分、应收应付核销），三表 = 分录汇总，试算平衡真实可校验
- **审计规则 12 条**（`app/services/audit.py`）：勾稽、发票号格式（8/20 位）、日期合理性、金额异常值、税率反推、schema 留痕等
- **evals 安全门**（`evals/samples/` + `tests/test_evals_gate.py`）：`unsafe_auto_approvals = 0` 断言，该拦未拦即测试失败
- **人工复核窗口**：明细表点击任意记录弹出编辑（33 个预设字段 + 审计提示），保存即重算三表
- **导出**：暂存表 xlsx / csv 导出；三表打印样式
- **双主题**：暖纸浅色 / 深色玻璃，弹簧动效，移动端适配

## 全链路

```
手机拍照（微信 ClawBot 通道已打通，见 wechat_bot/README.md）─→ 本地 Web App 接收图片
    → 多模态大模型 API 识别（预设字段输出，无则留空，多余信息归入「备注/其他」）
    → 暂存表入库（逐张留痕 · 时间序 · 可查重 · 可追溯）
    → 审计规则（勾稽校验 / 低置信度 → 人工复核队列）
    → 汇总计算 → 编制三表（资产负债表 / 利润表 / 现金流量表）
    → 每传一张即实时更新并向用户反馈
```

## 快速开始（一键启动）

- **Windows**：双击 `一键启动.bat` —— 自动检查 Python → 创建虚拟环境 → 安装依赖 → 启动服务并打开浏览器（http://127.0.0.1:8000）。停止：在窗口中按 `Ctrl + C` 或直接关窗。
- **macOS / Linux**：`bash 一键启动.sh`，流程同上。
- 仅首次运行需要联网安装依赖；之后双击即秒开。`requirements.txt` 更新后删除 `.venv\.deps_ok` 再启动即可重装。

手动方式：

```bash
pip install -r requirements.txt
python run.py          # 打开 http://127.0.0.1:8000
```

**零配置即可运行**：未配置 API 密钥时自动使用 Mock 演示端口，全链路（上传→识别→暂存→三表→反馈）完整可跑。

配置真实识别端口（复制 `.env.example` 为 `.env`）：

| 端口 | 说明 | 配置项 |
|---|---|---|
| 千问（首选，视觉主力） | DashScope OpenAI 兼容接口，`qwen-vl-max` | `RECOGNIZER_PROVIDER=qwen` + `QWEN_API_KEY` |
| DeepSeek（备选，文本环节实验） | 暂无视觉能力，用于 OCR 文本→字段复判 | `DEEPSEEK_API_KEY` |

## 目录结构

```
S.D.版本/
├── 一键启动.bat            # Windows 双击启动（自动建环境/装依赖/开浏览器）
├── 一键启动.sh             # macOS / Linux 一键启动
├── run.py                  # 启动入口（端口检测 + 自动打开浏览器）
├── requirements.txt
├── .env.example            # 配置模板（双 API 端口）
├── app/
│   ├── config.py           # 配置加载（本地优先）
│   ├── schemas.py          # 预设字段清单 + 数据模型（纯标准库）
│   ├── db.py               # 暂存表（SQLite）：留痕/查重/修正回流/来源统计
│   ├── main.py             # FastAPI 壳子：上传/明细/复核/三表接口
│   ├── services/
│   │   ├── recognizer.py   # 识别端口：qwen / deepseek / mock（可插拔）
│   │   ├── audit.py        # 审计规则：勾稽校验/置信度门/人工复核
│   │   ├── statements.py   # 汇总 + 三表编制（确定性科目映射）
│   │   └── pipeline.py     # 端到端编排：每传一张走完全程并反馈
│   ├── routers/
│   │   ├── admin.py        # 管理后台 API（配置/密钥检测/用量/日志）
│   │   └── bot.py          # 微信 Bot 通道（上传 + 连接自检 status/ping）
│   └── static/             # v0.4 SPA：侧边栏五页 + 弹簧动效 + 扁平 SVG 图标
├── wechat_bot/             # 微信 ClawBot 传话筒套件（转发脚本/技能/安装指南）
├── documents/designs/      # 设计系统文档（v3：iOS 舒适感取向）
└── tests/                  # test_pipeline（端到端）/ test_evals_gate（安全门）/ test_bot_endpoint（微信通道+自检）
```

## API 一览

| 方法 | 路径 | 说明 |
|---|---|---|
| POST | `/api/upload` | 上传票据图片 → 识别入账 → 返回最新三表 |
| POST | `/api/bot/upload` | 微信 Bot 通道上传（字节流 + `X-Bot-Token` 鉴权），返回微信回显文本 |
| GET | `/api/bot/status` | 微信连接自检（Node/Gateway/令牌 分步状态 + 入账统计） |
| GET | `/api/bot/ping` | 令牌回环自检（`X-Bot-Token` 头，不产生入账记录） |
| GET | `/api/records` | 暂存明细（历史查询，支持 `?status=review` 过滤） |
| GET | `/api/records/{id}` | 单条记录 + 修正历史 |
| PATCH | `/api/records/{id}` | 人工介入窗口：修正字段，回流留痕，重算三表 |
| GET | `/api/review` | 人工复核队列 |
| GET | `/api/statements` | 当前三大报表（实时重算） |
| GET | `/api/health` | 服务状态与当前识别端口 |

## 设计决策对应会议共识

| 会议共识 | 落地 |
|---|---|
| API 外接，不自研模型 | `recognizer.py` 可插拔端口，千问/DeepSeek 双版本实验 |
| 一款 API 一站式识别，预设格式输出 | 固定字段清单 + 无则留空 |
| 暂存表不可跳步 | SQLite 逐张留痕，时间序，发票代码+号码唯一索引查重 |
| 多余信息不删除 | 统一归入 `remarks` 备注/其他字段 |
| 实时反馈 | 每张上传后立即重算三表并返回状态（success/review/duplicate/failed） |
| 本地优先 | SQLite + 本地文件归档，数据不出本机 |
| 先通链路，呈现靠后 | 前端仅上传/明细/三表，Dashboard 留待 Phase 2 |
| 人工介入窗口 + 修正回流 | `/api/review` 队列 + `PATCH` 修正写入 `corrections` 留痕 |

## 已知边界（诚实说明）

- 三表为**小微企业简版口径**（科目→报表行的确定性映射），非完整会计准则实现；
- 微信通道依赖微信官方 ClawBot 插件（灰度中，要求 iOS ≥ 8.0.70）与 OpenClaw Gateway 常驻；Web 上传页仍作为兜底入口；
- Mock 端口仅用于链路演示，正式识别需配置千问 API 密钥。
