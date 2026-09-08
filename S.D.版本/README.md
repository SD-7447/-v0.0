# AI 中小微企业智能财务系统 · Phase 1（S.D.版本）

> 依据《企划书》（基础方针）与 2026-09-07 会议《Phase 1 开发计划》（落地方案）实现。
> 一句话目标：**做出可用的「壳子 + 全链路」——把票据照片变成三大报表**。

## 全链路

```
手机拍照（微信/扣子 Bot，攻关中）─→ 本地 Web App 接收图片
    → 多模态大模型 API 识别（预设字段输出，无则留空，多余信息归入「备注/其他」）
    → 暂存表入库（逐张留痕 · 时间序 · 可查重 · 可追溯）
    → 审计规则（勾稽校验 / 低置信度 → 人工复核队列）
    → 汇总计算 → 编制三表（资产负债表 / 利润表 / 现金流量表）
    → 每传一张即实时更新并向用户反馈
```

## 快速开始

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
├── run.py                  # 本地启动入口
├── requirements.txt
├── .env.example            # 配置模板（双 API 端口）
├── app/
│   ├── config.py           # 配置加载（本地优先）
│   ├── schemas.py          # 预设字段清单 + 数据模型（纯标准库）
│   ├── db.py               # 暂存表（SQLite）：留痕/查重/修正回流
│   ├── main.py             # FastAPI 壳子：上传/明细/复核/三表接口
│   ├── services/
│   │   ├── recognizer.py   # 识别端口：qwen / deepseek / mock（可插拔）
│   │   ├── audit.py        # 审计规则：勾稽校验/置信度门/人工复核
│   │   ├── statements.py   # 汇总 + 三表编制（确定性科目映射）
│   │   └── pipeline.py     # 端到端编排：每传一张走完全程并反馈
│   └── static/             # Apple 系美术基调前端（毛玻璃/扁平化/即时反馈）
└── tests/test_pipeline.py  # 端到端自测（Mock 端口，免密钥）
```

## API 一览

| 方法 | 路径 | 说明 |
|---|---|---|
| POST | `/api/upload` | 上传票据图片 → 识别入账 → 返回最新三表 |
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
- 微信 × 扣子 Bot 上传通道为会议列明的攻关项，本版本提供 Web 上传页作为兜底入口；
- Mock 端口仅用于链路演示，正式识别需配置千问 API 密钥。
