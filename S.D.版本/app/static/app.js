/* S.D. 智能财务 · Phase 1 前端逻辑 v2（主题切换 / 复核弹窗 / 实时反馈） */
const $ = (s) => document.querySelector(s);
const dz = $("#dzInner"), fileInput = $("#fileInput"), feed = $("#feed");
let currentTab = "income", currentFilter = "", lastStatements = null, reviewCount = 0;

/* ---------- 主题 ---------- */
const themeBtn = $("#themeToggle");
function applyTheme(t) {
  document.documentElement.dataset.theme = t;
  localStorage.setItem("sd-theme", t);
}
applyTheme(localStorage.getItem("sd-theme") || "paper");
themeBtn.addEventListener("click", () => {
  applyTheme(document.documentElement.dataset.theme === "dark" ? "paper" : "dark");
});

/* ---------- 上传 ---------- */
dz.addEventListener("click", () => fileInput.click());
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
    item.querySelector(".dot").className = "dot " + cls;
    item.querySelector("div").innerHTML = `<b>${icon} ${escapeHtml(data.message)}</b> <small>${escapeHtml(file.name)}</small>`;
    if (data.statements) { lastStatements = data.statements; renderStatements(); }
    loadRecords();
  } catch (err) {
    item.querySelector(".dot").className = "dot err";
    item.querySelector("div").innerHTML = `<b>❌ 网络错误</b><small>${escapeHtml(String(err))}</small>`;
  }
}

/* ---------- 三表 ---------- */
document.querySelectorAll(".tab").forEach((t) =>
  t.addEventListener("click", () => {
    document.querySelectorAll(".tab").forEach((x) => x.classList.remove("active"));
    t.classList.add("active");
    currentTab = t.dataset.tab;
    renderStatements();
  })
);

const TAB_KEYS = { income: "income_statement", balance: "balance_sheet", cashflow: "cashflow_statement" };

function renderStatements() {
  if (!lastStatements) return;
  const lines = lastStatements[TAB_KEYS[currentTab]] || [];
  const tbody = $("#stmtTable tbody");
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
  const bc = $("#balanceCheck");
  if (currentTab === "balance") {
    bc.textContent = lastStatements.balance_check ? "✓ 资产 = 负债 + 所有者权益（试算平衡）" : "✗ 借贷不平衡，请复核";
    bc.className = "check " + (lastStatements.balance_check ? "ok" : "bad");
  } else bc.textContent = "";
}

async function loadStatements() {
  lastStatements = await (await fetch("/api/statements")).json();
  renderStatements();
}

/* ---------- 暂存明细 ---------- */
document.querySelectorAll(".chip").forEach((c) =>
  c.addEventListener("click", () => {
    document.querySelectorAll(".chip").forEach((x) => x.classList.remove("active"));
    c.classList.add("active");
    currentFilter = c.dataset.filter;
    loadRecords();
  })
);

const ST_LABEL = { ok: ["已入账", "st-ok"], review: ["待复核", "st-review"], rejected: ["已拒收", "st-rejected"] };

async function loadRecords() {
  const url = "/api/records" + (currentFilter ? `?status=${currentFilter}` : "");
  const data = await (await fetch(url)).json();
  const tbody = $("#recordsTable tbody");
  tbody.innerHTML = "";
  let reviews = 0;
  data.records.forEach((r) => {
    const f = r.fields;
    if (r.status === "review") reviews++;
    const [label, cls] = ST_LABEL[r.status] || [r.status, ""];
    const tr = document.createElement("tr");
    tr.innerHTML = `
      <td>${r.id}</td>
      <td>${new Date(r.created_at).toLocaleString("zh-CN", { hour12: false })}</td>
      <td>${escapeHtml(f.invoice_type || "—")}</td>
      <td>${escapeHtml(f.invoice_number || "—")}</td>
      <td>${escapeHtml(f.category || "—")}</td>
      <td>${escapeHtml(f.direction || "—")}</td>
      <td class="num">${f.total_amount != null ? "¥ " + f.total_amount.toFixed(2) : "—"}</td>
      <td><span class="st ${cls}">${label}</span></td>
      <td class="remarks">${escapeHtml(f.remarks || "")}</td>`;
    tr.addEventListener("click", () => openModal(r));
    tbody.appendChild(tr);
  });
  $("#recordCount").textContent = data.records.length;
  const rb = $("#reviewBadge");
  rb.style.display = reviews ? "" : "none";
  rb.textContent = `${reviews} 待复核`;
}

/* ---------- 人工复核弹窗（G-15） ---------- */
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
  $("#modalMeta").textContent = `入库 ${new Date(r.created_at).toLocaleString("zh-CN")} · 状态 ${r.status} · 置信度 ${(f.confidence ?? 0).toFixed(2)}`;
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

$("#modalCancel").addEventListener("click", () => $("#modalMask").classList.remove("open"));
$("#modalMask").addEventListener("click", (e) => { if (e.target.id === "modalMask") $("#modalMask").classList.remove("open"); });

$("#modalSave").addEventListener("click", async () => {
  const updates = {};
  document.querySelectorAll("#modalForm [data-key]").forEach((el) => {
    const k = el.dataset.key;
    const v = el.value.trim();
    if (["amount", "tax_amount", "total_amount"].includes(k)) {
      updates[k] = v === "" ? null : parseFloat(v);
    } else updates[k] = v;
  });
  const resp = await fetch(`/api/records/${editingId}`, {
    method: "PATCH", headers: { "Content-Type": "application/json" }, body: JSON.stringify(updates),
  });
  const data = await resp.json();
  if (resp.ok) {
    addFeed("修正", "ok", "✅", data.message);
    if (data.statements) { lastStatements = data.statements; renderStatements(); }
    $("#modalMask").classList.remove("open");
    loadRecords();
  } else {
    $("#modalAudit").textContent = "保存失败：" + (data.detail || data.message || "未知错误");
  }
});

/* ---------- 健康检查 ---------- */
async function ping() {
  try {
    const h = await (await fetch("/api/health")).json();
    const el = $("#health");
    el.textContent = `● 正常 · 端口：${h.recognizer}`;
    el.classList.add("on");
  } catch {
    $("#health").textContent = "○ 服务未连接";
  }
}

function escapeHtml(s) {
  return String(s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}

ping(); loadStatements(); loadRecords();
setInterval(() => { loadStatements(); loadRecords(); }, 30000);
