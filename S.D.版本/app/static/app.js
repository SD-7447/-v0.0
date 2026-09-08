/* S.D. 智能财务 · Phase 1 前端逻辑 */
const $ = (s) => document.querySelector(s);
const dz = $("#dzInner"), fileInput = $("#fileInput"), feed = $("#feed");
let currentTab = "income", currentFilter = "", lastStatements = null;

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
    const dot = item.querySelector(".dot");
    const box = item.querySelector("div");
    const map = { success: ["ok", "✅"], review: ["warn", "⚠️"], duplicate: ["warn", "🔁"], failed: ["err", "❌"] };
    const [cls, icon] = map[data.status] || ["err", "❌"];
    dot.className = "dot " + cls;
    box.innerHTML = `<b>${icon} ${escapeHtml(data.message)}</b> <small>${escapeHtml(file.name)}</small>`;
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
    const isTotal = /总计|净额|净利润|余额/.test(l.label);
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
    bc.textContent = lastStatements.balance_check ? "✓ 资产 = 负债 + 所有者权益" : "✗ 借贷不平衡，请复核";
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
  data.records.forEach((r) => {
    const f = r.fields;
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
      <td><span class="st ${cls}" title="${escapeHtml(r.audit_notes)}">${label}</span></td>
      <td class="remarks">${escapeHtml(f.remarks || "")}</td>`;
    tbody.appendChild(tr);
  });
  $("#recordCount").textContent = data.records.length;
}

/* ---------- 健康检查 ---------- */
async function ping() {
  try {
    const h = await (await fetch("/api/health")).json();
    const el = $("#health");
    el.textContent = `● 本地服务正常 · 识别端口：${h.recognizer}`;
    el.classList.add("on");
  } catch {
    $("#health").textContent = "○ 服务未连接";
  }
}

function escapeHtml(s) {
  return String(s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}

ping(); loadStatements(); loadRecords();
setInterval(loadStatements, 30000);
