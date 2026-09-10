# v0.6 大改 · 严格对照 ios-visual-design skill 全库的执行记录

> 基准：`ios-visual-design` skill 完整版（2026-09-10 快照，SKILL.md + 13 篇 references + apple-tokens.css，全部通读）
> 对象：S.D. 智能财务 Web 端（`app/static/`）
> 平台判定：桌面优先、兼容移动端的 Web 应用（skill 未指定平台时以 iOS 为工作假设；文本密度按 macOS 惯例）
> 日期：2026-09-10

---

## 一、大改项与 skill 出处对照

### 1. Liquid Glass 导航层（本轮核心视觉变更）

| skill 依据 | 落地 |
|---|---|
| materials.md：「Liquid Glass 只承载悬浮的导航和关键功能」「regular 变体适合复杂背景或大量文字（提醒、**边栏**、弹出窗口）」 | 侧边栏 / 移动端底栏改为玻璃近似：`blur(28px) saturate(1.8)` + 半透明底色（dark `rgba(28,28,30,.55)` / paper `rgba(255,255,255,.60)`，取自 apple-tokens.css `.liquid-glass` 原型变量） |
| layout.md：「标签页栏、边栏等导航控件**悬浮在内容层之上**（而非同一平面）」「内容滚动到控件区域下方时保持连续」 | `.main` 取消 margin-left 占满全宽，`.page` 以 `padding-left: calc(sidebar + 28px)` 留出阅读区——**滚动时卡片从玻璃侧边栏下方透视穿过**；移动端同理，内容延伸到底栏玻璃下 |
| accessibility.md / foundations-review：「降低透明度设置下材质依然可读」 | 新增 `@media (prefers-reduced-transparency: reduce)`：侧边栏回退实心 `--card`，弹窗遮罩去模糊加深底色 |
| visual-playbook H：「不能仅加 backdrop-filter 就声称实现原生 Liquid Glass」 | 本文为**原型近似**，变量注释中明示；内容层（卡片）不使用玻璃，符合「内容层用标准材质」 |

### 2. 状态系统补全（默认/聚焦/按压/选中/不可用/加载/空/失败/成功）

| skill 依据 | 落地 |
|---|---|
| components.md 空状态：「友好符号 + 一句话说明 + 后续步骤/主操作按钮；不要只留空白」 | 新增 `.empty` 组件：明细无记录→「暂无票据 + 去上传」；搜索无结果→「没有匹配的票据 + 清除搜索」；报表无数据→「还没有可编制的报表 + 去上传」 |
| patterns.md loading：「先显示与最终布局一致的占位，避免空白或内容大幅跳动」 | 新增 `.sk` 骨架屏：明细表 6 行、报表 10 行 shimmer 占位，数据到达后原位替换 |
| components.md 按钮：「iOS 可在按钮内显示延迟状态」 | 复核保存按钮提交中显示内联 spinner「保存中…」+ busy 态防重复提交；新增 `.btn:disabled/.busy` 不可用样式 |
| patterns-inputs-review keyboards：「焦点环清晰、无陷阱；所有核心功能可仅用键盘完成」 | 全部可点元素（导航/chips/按钮/连接灯/上传区）新增 `:focus-visible` 双层焦点环；上传区获得 `tabindex/role=button` + Enter/空格触发 |
| interaction.md 触感：「语义化使用：成功/错误；克制」 | `navigator.vibrate`：上传成功轻振 15ms，失败/拒收双振 [40,60,40]；仅支持设备生效，桌面静默 |

### 3. 明细页搜索栏

| skill 依据 | 落地 |
|---|---|
| components.md search-fields：「占位文本说明搜索范围」「键入即搜」「支持清除」；patterns.md searching：「版块明确的 App 可提供局部过滤」 | 明细卡片工具区新增搜索框：占位「搜索发票号码 / 科目 / 备注」；键入即前端过滤（号码/科目/备注/类型/销售方/文件名）；有文字时出现圆形清除按钮；与状态筛选 chips（scope bar 角色）共存不冲突 |

### 4. 启动与状态恢复

| skill 依据 | 落地 |
|---|---|
| patterns.md launching：「重新启动后恢复之前的状态（细枝末节都恢复）」 | 当前页面写入 localStorage，无 hash 访问时恢复上次浏览的页面（主题恢复为既有能力） |

## 二、交付前核对（skill SKILL.md 清单逐项）

- [x] 主要任务、导航语义和反馈清晰，关闭与返回不混淆：五页平级导航；弹窗「取消/完成」前后缘分离；连接向导「暂不连接」出口
- [x] 常规文字对比度 ≥4.5:1：见 hig-audit-v0.4.md 第二节核算表（本轮未改动色板，结论沿用）
- [x] 颜色不是唯一线索：状态=色+文字+图标；连接灯=色点+文字；向导步骤=色+序号/对勾
- [x] 大字号重排可用：卡片/表格为流式布局，导航项 44px 可容纳文本放大
- [x] 命中区域足够：移动端全部 ≥44px，桌面 ≥36px（macOS 下限 28）
- [x] 键盘不遮挡当前输入：Web 表单由浏览器处理；弹窗 max-height 86vh 内部滚动
- [x] 复杂背景/降低透明度/增强对比度：降低透明度已有实心回退；玻璃层仅导航层，内容层不透明
- [x] 减弱动态效果：全部弹簧/位移降级 150ms 淡入淡出；骨架 shimmer 静止；进度环保留（进行中的必要信息）
- [x] 图标光学居中、笔画一致（全套 1.6px 描边 round cap 24 视窗）、含义正确（房子=首页、列表=明细、柱状=报表、对话泡=连接、齿轮=设置），未挪用 SF Symbols 受保护符号
- [x] 相关外观已测：dark/paper 双主题 × 桌面/移动断点；RTL 与 visionOS/watchOS 不适用（Web 中文产品），明确注明未测试
- [x] 来源可追溯：每项改动上表均有 skill 文件出处；未把原型变量声称为官方实现

## 三、验证结果

- `node --check app/static/app.js`：通过
- 临时端口 8018 实测：`/` 200、`/static/style.css` 200、`/static/app.js` 200、`/api/bot/status` 正常 JSON；测后进程已结束
- 三个测试脚本（微信通道 / 端到端流水线 / evals 安全门）：全部通过
- GitHub 已同步并核验字节数一致

## 四、延续说明

- v0.5 的 4 项有意偏离（App 内主题切换 / 暖纸浅色 / 胶囊按钮 / 桌面 13pt 正文）本轮继续保留，理由见 hig-audit-v0.4.md 第四节
- 报表页暂不提供图表：patterns.md charting-data「只陈列原始数据时优先列表/表格」——三表为科目原始数据，表格为正确组件；趋势图表属 Phase 2 Dashboard 范围
