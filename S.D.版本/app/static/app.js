/* S.D. 智能财务 · 前端 v3（SPA 路由 / 弹簧过渡 / 微信连接向导） */
const $ = (s) => document.querySelector(s);
const $$ = (s) => document.querySelectorAll(s);

/* ---------- 主题 ---------- */
function applyTheme(t) {
  document.documentElement.dataset.theme = t;
  localStorage.setItem("sd-theme", t);
}
applyTheme(localStorage.getItem("sd-theme") || "dark");
$("#themeToggle").addEventListener("click", () => {
  applyTheme(document.documentElement.dataset.theme === "dark" ? "paper" : "dark");
});

/* ---------- SPA 路由（方向感弹簧过渡） ---------- */
const PAGES = ["home", "records", "reports", "connect", "settings"];
let currentPage = "home", switching = false;

function goTo(page) {
  if (page === currentPage || switching || !PAGES.includes(page)) return;
  switching = true;
  const oldIdx = PAGES.indexOf(currentPage), newIdx = PAGES.indexOf(page);
  const back = newIdx < oldIdx;
  const oldEl = $("#page-" + currentPage), newEl = $("#page-" + page);

  $$(".nav-item").forEach((n) => n.classList.toggle("active", n.dataset.page === page));
  oldEl.classList.remove("page-enter", "back");
  oldEl.classList.add("page-leave");
  if (back) oldEl.classList.add("back");

  setTimeout(() => {
    oldEl.classList.remove("active", "page-leave", "back");
    newEl.classList.add("active");
    newEl.classList.remove("page-enter", "back");
    void newEl.offsetWidth;               // 重启动画
    newEl.classList.add("page-enter");
    if (back) newEl.classList.add("back");
    $("#main").scrollTop = 0;
    currentPage = page;
    history.replaceState(null, "", "#" + page);
    localStorage.setItem("sd-page", page);
    onPageShow(page);
    setTimeout(() => (switching = false), 380);
  }, 180);                                 // 让旧页面先动出一半，节奏更连贯
}

$$(".nav-item").forEach((n) => n.addEventListener("click", () => goTo(n.dataset.page)));

function onPageShow(page) {
  if (page === "home") loadHomeKpis();
  if (page === "records") loadRecords();
  if (page === "reports") loadStatements();
  if (page === "connect") refreshConnStatus();
  if (page === "settings") { loadConfig(); loadStats(); loadUsage(); loadLogs(); }
}

/* ---------- 上传 ---------- */
const dz = $("#dz"), fileInput = $("#fileInput"), feed = $("#feed");
dz.addEventListener("click", () => fileInput.click());
dz.addEventListener("keydown", (e) => {                    // 键盘可达：Enter/空格触发上传
  if (e.key === "Enter" || e.key === " ") { e.preventDefault(); fileInput.click(); }
});
/* 语义化触觉反馈（HIG haptics：成功轻振 / 失败双振；仅支持的移动设备生效） */
function haptic(pattern) { if (navigator.vibrate) { try { navigator.vibrate(pattern); } catch { /* 不支持则静默 */ } } }
dz.addEventListener("dragover", (e) => { e.preventDefault(); dz.classList.add("over"); });
dz.addEventListener("dragleave", () => dz.classList.remove("over"));
dz.addEventListener("drop", (e) => {
  e.preventDefault(); dz.classList.remove("over");
  [...e.dataTransfer.files].forEach(uploadOne);
});
fileInput.addEventListener("change", () => [...fileInput.files].forEach(uploadOne));

function addFeed(fileName, cls, title, sub = "") {
  const li = document.createElement("li");
  li.innerHTML = `<span class="dot ${cls}"></span><div><b>${title}</b> ${escapeHtml(fileName)}${sub ? `<small>${escapeHtml(sub)}</small>` : ""}</div>`;
  feed.prepend(li);
  return li;
}

async function uploadOne(file) {
  const item = addFeed(file.name, "run", "识别中…", "正在调用视觉识别端口");
  const fd = new FormData();
  fd.append("file", file);
  try {
    const resp = await fetch("/api/upload", { method: "POST", body: fd });
    const data = await resp.json();
    const map = { success: ["ok", "✅"], review: ["warn", "⚠️"], duplicate: ["warn", "🔁"], failed: ["err", "❌"] };
    const [cls, icon] = map[data.status] || ["err", "❌"];
    haptic(data.status === "success" ? 15 : [40, 60, 40]);
    item.querySelector(".dot").className = "dot " + cls;
    item.querySelector("div").innerHTML = `<b>${icon} ${escapeHtml(data.message)}</b> <small>${escapeHtml(file.name)}</small>`;
    loadHomeKpis();
    if (currentPage === "records") loadRecords();
    if (currentPage === "reports") loadStatements();
  } catch (err) {
    haptic([40, 60, 40]);
    item.querySelector(".dot").className = "dot err";
    item.querySelector("div").innerHTML = `<b>❌ 网络错误</b><small>${escapeHtml(String(err))}</small>`;
  }
}

async function loadHomeKpis() {
  try {
    const s = await (await fetch("/api/admin/stats")).json();
    $("#homeKpis").innerHTML = [
      [s.records.total, "票据总数", ""], [s.records.ok, "已入账", "ok"],
      [s.records.review, "待复核", "warn"], [s.records.rejected, "已拒收", "err"],
    ].map(([v, k, c]) => `<div class="kpi"><div class="v ${c}">${v ?? 0}</div><div class="k">${k}</div></div>`).join("");
  } catch { /* 服务未就绪时静默 */ }
}

/* ---------- 明细（搜索 / 筛选 / 空状态 / 骨架屏） ---------- */
let currentFilter = "", lastRecords = [], searchText = "";
$$(".filters .chip").forEach((c) =>
  c.addEventListener("click", () => {
    $$(".filters .chip").forEach((x) => x.classList.remove("active"));
    c.classList.add("active");
    currentFilter = c.dataset.filter;
    loadRecords();
  })
);

/* 搜索栏：键入即搜（HIG search-fields：占位说明范围、可清除） */
const searchInput = $("#searchInput"), searchWrap = $("#searchWrap");
searchInput.addEventListener("input", () => {
  searchText = searchInput.value.trim().toLowerCase();
  searchWrap.classList.toggle("has-text", !!searchText);
  renderRecords();
});
$("#searchClear").addEventListener("click", () => {
  searchInput.value = ""; searchText = ""; searchWrap.classList.remove("has-text");
  renderRecords(); searchInput.focus();
});

const ST_LABEL = { ok: ["已入账", "st-ok"], review: ["待复核", "st-review"], rejected: ["已拒收", "st-rejected"] };

/* 空状态（HIG：友好符号 + 一句话说明 + 可执行下一步） */
const EMPTY_ICONS = {
  tray: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"><path d="M3 13 5.5 5h13L21 13v6a1.5 1.5 0 0 1-1.5 1.5h-15A1.5 1.5 0 0 1 3 19z"/><path d="M3 13h5.5l1.5 2.5h4L15.5 13H21"/></svg>',
  search: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round"><circle cx="11" cy="11" r="7"/><path d="m20.5 20.5-4.5-4.5"/><path d="m8.5 8.5 5 5M13.5 8.5l-5 5"/></svg>',
};
function emptyState(icon, title, sub, action = "") {
  return `<div class="empty">${EMPTY_ICONS[icon]}<div class="et">${title}</div><div class="es">${sub}</div>${action}</div>`;
}

function skRows(cols, n) {
  return Array.from({ length: n }, () =>
    `<tr><td colspan="${cols}" style="border-bottom:none;padding:9px 10px"><div class="sk"></div></td></tr>`).join("");
}

async function loadRecords() {
  const tbody = $("#recordsTable tbody");
  $("#recordsTable").style.display = "";
  $("#recordsEmpty").innerHTML = "";
  tbody.innerHTML = skRows(10, 6);                    // 骨架占位：与最终布局一致
  const url = "/api/records" + (currentFilter ? `?status=${currentFilter}` : "");
  const data = await (await fetch(url)).json();
  lastRecords = data.records;
  renderRecords();
}

function renderRecords() {
  const q = searchText;
  const rows = q
    ? lastRecords.filter((r) => {
        const f = r.fields;
        return [f.invoice_number, f.category, f.remarks, f.invoice_type, f.seller_name, r.file_name]
          .filter(Boolean).some((v) => String(v).toLowerCase().includes(q));
      })
    : lastRecords;
  const tbody = $("#recordsTable tbody");
  const emptyEl = $("#recordsEmpty");
  tbody.innerHTML = "";
  if (!rows.length) {
    $("#recordsTable").style.display = "none";
    emptyEl.innerHTML = q
      ? emptyState("search", "没有匹配的票据", `没有找到包含「${escapeHtml(searchText)}」的记录，换个关键词或清除搜索。`, `<button class="btn" id="emptyClearSearch">清除搜索</button>`)
      : emptyState("tray", "暂无票据", "拍张照或拖入票据图片，系统会自动识别并更新三表。", `<button class="btn primary" id="emptyGoUpload">去上传</button>`);
    const b1 = $("#emptyClearSearch");
    if (b1) b1.addEventListener("click", () => $("#searchClear").click());
    const b2 = $("#emptyGoUpload");
    if (b2) b2.addEventListener("click", () => goTo("home"));
  } else {
    $("#recordsTable").style.display = "";
    emptyEl.innerHTML = "";
    rows.forEach((r, i) => {
      const f = r.fields;
      const [label, cls] = ST_LABEL[r.status] || [r.status, ""];
      const tr = document.createElement("tr");
      tr.style.animation = `cardIn .35s cubic-bezier(.34,1.4,.44,1) ${Math.min(i * 30, 300)}ms backwards`;
      tr.innerHTML = `
        <td>${r.id}</td>
        <td>${new Date(r.created_at).toLocaleString("zh-CN", { hour12: false })}</td>
        <td>${escapeHtml(f.invoice_type || "—")}</td>
        <td>${escapeHtml(f.invoice_number || "—")}</td>
        <td>${escapeHtml(f.category || "—")}</td>
        <td>${escapeHtml(f.direction || "—")}</td>
        <td class="num">${f.total_amount != null ? "¥ " + f.total_amount.toFixed(2) : "—"}</td>
        <td><span class="st ${cls}">${label}</span></td>
        <td><span class="src src-${r.source === "wechat" ? "wechat" : "web"}">${r.source === "wechat" ? "微信" : "网页"}</span></td>
        <td class="remarks">${escapeHtml(f.remarks || "")}</td>`;
      tr.addEventListener("click", () => openModal(r));
      tbody.appendChild(tr);
    });
  }
  $("#recordCount").textContent = rows.length;
  const reviews = lastRecords.filter((r) => r.status === "review").length;
  const rb = $("#reviewBadge");
  rb.style.display = reviews ? "" : "none";
  rb.textContent = `${reviews} 待复核`;
}

/* ---------- 报表 ---------- */
let currentTab = "income", lastStatements = null;
const TAB_KEYS = { income: "income_statement", balance: "balance_sheet", cashflow: "cashflow_statement" };
$$("#page-reports .tabs .chip").forEach((t) =>
  t.addEventListener("click", () => {
    $$("#page-reports .tabs .chip").forEach((x) => x.classList.remove("active"));
    t.classList.add("active");
    currentTab = t.dataset.tab;
    renderStatements();
  })
);
$("#printBtn").addEventListener("click", () => window.print());

function renderStatements() {
  if (!lastStatements) return;
  const tbody = $("#stmtTable tbody");
  const emptyEl = $("#stmtEmpty");
  const bc = $("#balanceCheck");
  /* 空状态：没有票据时给可执行下一步（HIG empty state） */
  if (!lastStatements.record_count) {
    $("#stmtTable").style.display = "none";
    $("#stmtMeta").textContent = "暂无数据";
    bc.textContent = "";
    emptyEl.innerHTML = emptyState("tray", "还没有可编制的报表", "上传第一张票据后，三大报表会在这里实时生成。", `<button class="btn primary" id="emptyGoUpload2">去上传</button>`);
    const b = $("#emptyGoUpload2");
    if (b) b.addEventListener("click", () => goTo("home"));
    return;
  }
  $("#stmtTable").style.display = "";
  emptyEl.innerHTML = "";
  const lines = lastStatements[TAB_KEYS[currentTab]] || [];
  tbody.innerHTML = "";
  lines.forEach((l) => {
    const tr = document.createElement("tr");
    const isTotal = /总计|合计|净额|净利润|余额/.test(l.label);
    const isHeader = /^——/.test(l.label);
    if (isTotal) tr.className = "total";
    if (isHeader) {
      tr.innerHTML = `<td colspan="2" style="color:var(--sub);font-weight:700">${escapeHtml(l.label)}</td>`;
    } else {
      tr.innerHTML = `<td>${escapeHtml(l.label)}</td><td>¥ ${l.amount.toLocaleString("zh-CN", { minimumFractionDigits: 2 })}</td>`;
    }
    tbody.appendChild(tr);
  });
  $("#stmtMeta").textContent = `共 ${lastStatements.record_count} 张票据 · 更新于 ${new Date(lastStatements.generated_at).toLocaleTimeString("zh-CN")}`;
  if (currentTab === "balance") {
    bc.textContent = lastStatements.balance_check ? "✓ 资产 = 负债 + 所有者权益（试算平衡）" : "✗ 借贷不平衡，请复核";
    bc.className = "check " + (lastStatements.balance_check ? "ok" : "bad");
  } else bc.textContent = "";
}

async function loadStatements() {
  const tbody = $("#stmtTable tbody");
  $("#stmtTable").style.display = "";
  $("#stmtEmpty").innerHTML = "";
  tbody.innerHTML = skRows(2, 10);                    // 骨架占位
  lastStatements = await (await fetch("/api/statements")).json();
  renderStatements();
}

/* ---------- 复核弹窗 ---------- */
const EDITABLE = [
  ["invoice_type", "发票/票据类型"], ["invoice_number", "发票号码"], ["invoice_date", "开票日期(YYYY-MM-DD)"],
  ["seller_name", "销售方名称"], ["buyer_name", "购买方名称"], ["item_name", "货物或服务名称"],
  ["amount", "金额(不含税)"], ["tax_amount", "税额"], ["total_amount", "价税合计"],
  ["category", "会计科目"], ["payment_method", "收付款方式"], ["invoice_status", "发票状态"],
];
let editingId = null;

function openModal(r) {
  editingId = r.id;
  const f = r.fields;
  $("#modalTitle").textContent = `记录 #${r.id} · ${r.file_name}`;
  $("#modalMeta").textContent = `入库 ${new Date(r.created_at).toLocaleString("zh-CN")} · 状态 ${r.status} · 来源 ${r.source === "wechat" ? "微信" : "网页"} · 置信度 ${(f.confidence ?? 0).toFixed(2)}`;
  const notes = [r.audit_notes, f.validation_notes].filter(Boolean).join("；");
  $("#modalAudit").textContent = notes ? "审计提示：" + notes : "";
  const form = $("#modalForm");
  form.innerHTML = "";
  EDITABLE.forEach(([key, label]) => {
    const div = document.createElement("div");
    const val = f[key] ?? "";
    div.innerHTML = `<label>${label}</label><input data-key="${key}" value="${escapeHtml(String(val))}">`;
    form.appendChild(div);
  });
  const dirDiv = document.createElement("div");
  dirDiv.innerHTML = `<label>收支方向</label>
    <select data-key="direction">
      <option value="" ${f.direction === "" ? "selected" : ""}>（未确定）</option>
      <option value="收入" ${f.direction === "收入" ? "selected" : ""}>收入</option>
      <option value="支出" ${f.direction === "支出" ? "selected" : ""}>支出</option>
    </select>`;
  form.appendChild(dirDiv);
  const remDiv = document.createElement("div");
  remDiv.className = "full";
  remDiv.innerHTML = `<label>备注/其他</label><textarea data-key="remarks" rows="2">${escapeHtml(f.remarks || "")}</textarea>`;
  form.appendChild(remDiv);
  $("#modalMask").classList.add("open");
}

function closeMask(mask) {
  mask.classList.add("closing");
  setTimeout(() => mask.classList.remove("open", "closing"), 300);
}
$("#modalCancel").addEventListener("click", () => closeMask($("#modalMask")));
$("#modalMask").addEventListener("click", (e) => { if (e.target.id === "modalMask") closeMask($("#modalMask")); });

$("#modalSave").addEventListener("click", async () => {
  const saveBtn = $("#modalSave");
  if (saveBtn.classList.contains("busy")) return;
  const updates = {};
  $$("#modalForm [data-key]").forEach((el) => {
    const k = el.dataset.key;
    const v = el.value.trim();
    if (["amount", "tax_amount", "total_amount"].includes(k)) {
      updates[k] = v === "" ? null : parseFloat(v);
    } else updates[k] = v;
  });
  /* 按钮内活动指示（HIG buttons：无需另开弹层），并防重复提交 */
  saveBtn.classList.add("busy");
  const origText = saveBtn.textContent;
  saveBtn.innerHTML = '<span class="spin"></span> 保存中…';
  try {
    const resp = await fetch(`/api/records/${editingId}`, {
      method: "PATCH", headers: { "Content-Type": "application/json" }, body: JSON.stringify(updates),
    });
    const data = await resp.json();
    if (resp.ok) {
      addFeed("修正", "ok", "✅", data.message);
      closeMask($("#modalMask"));
      loadRecords(); loadHomeKpis();
    } else {
      $("#modalAudit").textContent = "保存失败：" + (data.detail || data.message || "未知错误");
    }
  } catch (err) {
    $("#modalAudit").textContent = "保存失败：网络错误，请稍后重试";
  } finally {
    saveBtn.classList.remove("busy");
    saveBtn.textContent = origText;
  }
});

/* ---------- 微信连接：状态 + 向导 ---------- */
const STEP_DEFS = [
  { key: "node", name: "Node.js 环境", desc: '转发脚本运行环境（≥ 18）。未安装：到 <code>nodejs.org</code> 下载 LTS 版。' },
  { key: "gateway", name: "OpenClaw Gateway 常驻", desc: '运行 <code>openclaw gateway</code> 保持常驻。未装 ClawBot 插件：执行 <code>npx -y @tencent-weixin/openclaw-weixin-cli@latest install</code>，并用微信（iOS ≥ 8.0.70）扫码绑定。' },
  { key: "token", name: "令牌配对（BOT_TOKEN）", desc: '在本页输入令牌保存后，于 Gateway 机器设置环境变量 <code>SD_BOT_TOKEN</code> 为同一值。' },
];
const CHECK_SVG = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"><path d="m4 12.5 5 5L20 6.5"/></svg>';

function renderSteps(container, steps, { wizard = false } = {}) {
  const el = typeof container === "string" ? $(container) : container;
  el.innerHTML = "";
  const firstFail = STEP_DEFS.findIndex((s) => !steps[s.key]);
  STEP_DEFS.forEach((s, i) => {
    const state = steps[s.key] ? "done" : (i === firstFail ? "doing" : "");
    const div = document.createElement("div");
    div.className = "step " + state;
    let action = "";
    if (wizard && s.key === "token" && !steps.token) {
      action = `<div class="step-action" style="display:flex;gap:8px">
        <input id="wizardToken" placeholder="输入令牌（留空则跳过）" style="flex:1">
        <button class="btn" id="wizardSaveToken">保存</button></div>`;
    }
    div.innerHTML = `
      <div class="step-dot">${steps[s.key] ? CHECK_SVG : i + 1}</div>
      <div><div class="step-name">${s.name}</div><div class="step-desc">${s.desc}</div>${action}</div>`;
    el.appendChild(div);
  });
  if (wizard && !steps.token) {
    const btn = $("#wizardSaveToken");
    if (btn) btn.addEventListener("click", saveWizardToken);
  }
}

async function saveWizardToken() {
  const v = $("#wizardToken").value.trim();
  if (!v) return;
  await fetch("/api/admin/config", {
    method: "PUT", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ BOT_TOKEN: v }),
  });
  refreshConnStatus();
}

function renderConnHero(heroSel, titleSel, subSel, st) {
  const hero = $(heroSel);
  hero.classList.toggle("ok", st.connected);
  $(titleSel).textContent = st.connected ? "微信通道已连接" : (st.partial ? "通道可达 · 未加密" : "微信通道未连接");
  $(subSel).textContent = st.connected
    ? `累计微信入账 ${st.wechat_count} 张${st.last_wechat_at ? " · 最近 " + new Date(st.last_wechat_at).toLocaleString("zh-CN", { hour12: false }) : ""}`
    : (st.partial ? "Gateway 在运行，但未配置 BOT_TOKEN，任何本机程序都可上传，建议完成令牌配对" : "按下方步骤完成连接，系统将自动检测");
}

let connTimer = null;

async function refreshConnStatus() {
  let st;
  try {
    st = await (await fetch("/api/bot/status")).json();
  } catch {
    return null;
  }
  renderConnHero("#connHero", "#connTitle", "#connSub", st);
  renderSteps("#connSteps", st.steps);
  const pill = $("#connPill");
  pill.classList.toggle("ok", st.connected);
  pill.classList.toggle("bad", !st.connected);
  $("#connPillText").textContent = st.connected ? "微信已连接" : "微信未连接";
  return st;
}

/* 向导弹窗：打开即开始每 3 秒轮询，连接成功后展示 ✓ 并自动回收 */
function openWizard() {
  const mask = $("#connMask");
  mask.classList.add("open");
  wizardTick();
  clearInterval(connTimer);
  connTimer = setInterval(wizardTick, 3000);
}

async function wizardTick() {
  let st;
  try {
    st = await (await fetch("/api/bot/status")).json();
  } catch { return; }
  renderConnHero("#wizardHero", "#wizardTitle", "#wizardSub", st);
  if (st.connected) {
    $("#wizardSub").textContent = "连接成功，弹窗即将自动关闭";
    renderSteps("#wizardSteps", st.steps, { wizard: true });
    clearInterval(connTimer);
    refreshConnStatus();
    setTimeout(() => closeMask($("#connMask")), 1400);
  } else {
    renderSteps("#wizardSteps", st.steps, { wizard: true });
  }
}

$("#recheckBtn").addEventListener("click", refreshConnStatus);
$("#openWizardBtn").addEventListener("click", openWizard);
$("#wizardRecheck").addEventListener("click", wizardTick);
$("#wizardLater").addEventListener("click", () => {
  clearInterval(connTimer);
  closeMask($("#connMask"));
  sessionStorage.setItem("sd-conn-dismissed", "1");
});
$("#connPill").addEventListener("click", () => goTo("connect"));

/* 启动自检：未连接且本次会话未手动跳过 → 弹出向导 */
async function bootConnCheck() {
  if (sessionStorage.getItem("sd-conn-dismissed")) { refreshConnStatus(); return; }
  const st = await refreshConnStatus();
  if (st && !st.connected) openWizard();
}

/* ---------- 设置页 ---------- */
async function loadConfig() {
  const data = await (await fetch("/api/admin/config")).json();
  const c = data.config;
  $("#cfgProvider").value = c.RECOGNIZER_PROVIDER || "mock";
  $("#activeRecognizer").value = data.active_recognizer;
  $("#qwenKey").placeholder = c.QWEN_API_KEY ? `当前：${c.QWEN_API_KEY}（留空保持不变）` : "未配置";
  $("#qwenModel").value = c.QWEN_MODEL || "";
  $("#dsKey").placeholder = c.DEEPSEEK_API_KEY ? `当前：${c.DEEPSEEK_API_KEY}（留空保持不变）` : "未配置";
  $("#dsModel").value = c.DEEPSEEK_MODEL || "";
  $("#botToken").placeholder = c.BOT_TOKEN ? `当前：${c.BOT_TOKEN}（留空保持不变）` : "未配置（微信上传不鉴权）";
}

$("#saveConfig").addEventListener("click", async () => {
  const patch = { RECOGNIZER_PROVIDER: $("#cfgProvider").value };
  if ($("#qwenKey").value.trim()) patch.QWEN_API_KEY = $("#qwenKey").value.trim();
  if ($("#qwenModel").value.trim()) patch.QWEN_MODEL = $("#qwenModel").value.trim();
  if ($("#dsKey").value.trim()) patch.DEEPSEEK_API_KEY = $("#dsKey").value.trim();
  if ($("#dsModel").value.trim()) patch.DEEPSEEK_MODEL = $("#dsModel").value.trim();
  if ($("#botToken").value.trim()) patch.BOT_TOKEN = $("#botToken").value.trim();
  const resp = await fetch("/api/admin/config", {
    method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify(patch),
  });
  const data = await resp.json();
  if (resp.ok) {
    $("#qwenKey").value = ""; $("#dsKey").value = ""; $("#botToken").value = "";
    loadConfig();
    showTestResult({ ok: true, message: `已保存，当前生效端口：${data.active_recognizer}` });
  } else {
    showTestResult({ ok: false, message: "保存失败：" + (data.detail || "") });
  }
});

$$("[data-test]").forEach((btn) =>
  btn.addEventListener("click", async () => {
    const provider = btn.dataset.test;
    showTestResult({ ok: true, message: `正在检测 ${provider} …` });
    const payload = { provider };
    if (provider === "qwen") {
      if ($("#qwenKey").value.trim()) payload.api_key = $("#qwenKey").value.trim();
      if ($("#qwenModel").value.trim()) payload.model = $("#qwenModel").value.trim();
    }
    if (provider === "deepseek") {
      if ($("#dsKey").value.trim()) payload.api_key = $("#dsKey").value.trim();
      if ($("#dsModel").value.trim()) payload.model = $("#dsModel").value.trim();
    }
    const data = await (await fetch("/api/admin/test-provider", {
      method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload),
    })).json();
    showTestResult(data);
  })
);

function showTestResult(data) {
  const div = document.createElement("div");
  div.className = "test-result " + (data.ok ? "ok" : "bad");
  let extra = "";
  if (data.latency_ms != null) extra += ` · ${data.latency_ms}ms`;
  if (data.model_available === true) extra += ` · 模型 ${data.model} 可用`;
  if (data.model_available === false) extra += ` · ⚠ 模型 ${data.model} 不在可用列表`;
  div.textContent = `${data.ok ? "✅" : "❌"} [${data.provider || ""}] ${data.message}${extra}`;
  $("#testResults").prepend(div);
}

async function loadStats() {
  const s = await (await fetch("/api/admin/stats")).json();
  $("#kpis").innerHTML = [
    [s.records.total, "票据总数"], [s.records.ok, "已入账"], [s.records.review, "待复核"],
    [s.records.rejected, "已拒收"], [s.corrections, "人工修正"],
  ].map(([v, k]) => `<div class="kpi"><div class="v">${v}</div><div class="k">${k}</div></div>`).join("");
  $("#sysKv").innerHTML = [
    ["系统版本", "v" + s.version], ["Python", s.python], ["识别端口", s.active_recognizer],
    ["数据库大小", fmtBytes(s.storage.db_bytes)], ["图片归档", fmtBytes(s.storage.upload_bytes)],
  ].map(([k, v]) => `<div class="kv"><span>${k}</span><b>${v}</b></div>`).join("");
}

async function loadUsage() {
  const u = await (await fetch("/api/admin/usage")).json();
  const tbody = $("#usageTable tbody");
  tbody.innerHTML = "";
  Object.entries(u.by_provider).forEach(([p, r]) => {
    tbody.innerHTML += `<tr><td>${p}</td><td>${r.calls}</td><td>${r.successes}</td>
      <td>${r.prompt_tokens}</td><td>${r.completion_tokens}</td><td>${r.avg_latency_ms}ms</td></tr>`;
  });
  if (!tbody.innerHTML) tbody.innerHTML = `<tr><td colspan="6" style="color:var(--sub)">暂无调用记录</td></tr>`;
  const rt = $("#recentTable tbody");
  rt.innerHTML = "";
  u.recent.forEach((r) => {
    rt.innerHTML += `<tr><td>${(r.created_at || "").slice(5, 19).replace("T", " ")}</td><td>${r.provider}</td>
      <td>${r.model || "—"}</td><td>${r.prompt_tokens + r.completion_tokens}</td>
      <td>${r.latency_ms}ms</td><td>${r.success ? "✓" : "✗ " + escapeHtml(r.error.slice(0, 30))}</td></tr>`;
  });
  if (!rt.innerHTML) rt.innerHTML = `<tr><td colspan="6" style="color:var(--sub)">暂无记录</td></tr>`;
}

async function loadLogs() {
  const d = await (await fetch("/api/admin/logs?lines=120")).json();
  $("#logBox").textContent = d.lines.length ? d.lines.join("\n") : "暂无日志";
}
$("#refreshLogs").addEventListener("click", loadLogs);

$("#clearBtn").addEventListener("click", async () => {
  if (!confirm("确认清空暂存表？全部票据记录与修正历史将被删除！")) return;
  if (!confirm("二次确认：此操作不可撤销，原图归档会保留。仍要清空吗？")) return;
  const resp = await fetch("/api/admin/data/records?confirm=" + encodeURIComponent("清空"), { method: "DELETE" });
  const data = await resp.json();
  alert(data.message || data.detail || "完成");
  loadStats(); loadUsage(); loadLogs(); loadHomeKpis();
});

/* ---------- 工具 ---------- */
function fmtBytes(n) {
  if (n < 1024) return n + " B";
  if (n < 1048576) return (n / 1024).toFixed(1) + " KB";
  return (n / 1048576).toFixed(2) + " MB";
}
function escapeHtml(s) {
  return String(s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}

/* ---------- 启动 ---------- */
/* 启动恢复上次页面（HIG launching：重启后恢复之前状态） */
const initial = location.hash.slice(1) || localStorage.getItem("sd-page") || "home";
if (PAGES.includes(initial) && initial !== "home") {
  $("#page-home").classList.remove("active");
  $("#page-" + initial).classList.add("active");
  $$(".nav-item").forEach((n) => n.classList.toggle("active", n.dataset.page === initial));
  currentPage = initial;
  onPageShow(initial);
}
loadHomeKpis();
refreshConnStatus();
bootConnCheck();
setInterval(() => {
  if (currentPage === "records") loadRecords();
  if (currentPage === "reports") loadStatements();
}, 30000);
