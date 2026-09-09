/* S.D. 智能财务 · 管理后台逻辑 */
const $ = (s) => document.querySelector(s);

/* ---------- 主题 ---------- */
function applyTheme(t) {
  document.documentElement.dataset.theme = t;
  localStorage.setItem("sd-theme", t);
}
applyTheme(localStorage.getItem("sd-theme") || "paper");
$("#themeToggle").addEventListener("click", () => {
  applyTheme(document.documentElement.dataset.theme === "dark" ? "paper" : "dark");
});

/* ---------- 配置 ---------- */
async function loadConfig() {
  const data = await (await fetch("/api/admin/config")).json();
  const c = data.config;
  $("#cfgProvider").value = c.RECOGNIZER_PROVIDER || "mock";
  $("#activeRecognizer").value = data.active_recognizer;
  $("#qwenKey").placeholder = c.QWEN_API_KEY ? `当前：${c.QWEN_API_KEY}（留空保持不变）` : "未配置";
  $("#qwenModel").value = c.QWEN_MODEL || "";
  $("#dsKey").placeholder = c.DEEPSEEK_API_KEY ? `当前：${c.DEEPSEEK_API_KEY}（留空保持不变）` : "未配置";
  $("#dsModel").value = c.DEEPSEEK_MODEL || "";
}

$("#saveConfig").addEventListener("click", async () => {
  const patch = { RECOGNIZER_PROVIDER: $("#cfgProvider").value };
  if ($("#qwenKey").value.trim()) patch.QWEN_API_KEY = $("#qwenKey").value.trim();
  if ($("#qwenModel").value.trim()) patch.QWEN_MODEL = $("#qwenModel").value.trim();
  if ($("#dsKey").value.trim()) patch.DEEPSEEK_API_KEY = $("#dsKey").value.trim();
  if ($("#dsModel").value.trim()) patch.DEEPSEEK_MODEL = $("#dsModel").value.trim();
  const resp = await fetch("/api/admin/config", {
    method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify(patch),
  });
  const data = await resp.json();
  if (resp.ok) {
    $("#qwenKey").value = ""; $("#dsKey").value = "";
    loadConfig();
    showTestResult({ ok: true, message: `已保存，当前生效端口：${data.active_recognizer}` });
  } else {
    showTestResult({ ok: false, message: "保存失败：" + (data.detail || "") });
  }
});

/* ---------- Token 检测（先测后存：输入框里未保存的 key/模型也参与检测） ---------- */
document.querySelectorAll("[data-test]").forEach((btn) =>
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

/* ---------- 系统状态 ---------- */
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

/* ---------- 用量 ---------- */
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

/* ---------- 日志 ---------- */
async function loadLogs() {
  const d = await (await fetch("/api/admin/logs?lines=120")).json();
  $("#logBox").textContent = d.lines.length ? d.lines.join("\n") : "暂无日志";
}
$("#refreshLogs").addEventListener("click", loadLogs);

/* ---------- 危险操作 ---------- */
$("#clearBtn").addEventListener("click", async () => {
  if (!confirm("确认清空暂存表？全部票据记录与修正历史将被删除！")) return;
  if (!confirm("二次确认：此操作不可撤销，原图归档会保留。仍要清空吗？")) return;
  const resp = await fetch("/api/admin/data/records?confirm=" + encodeURIComponent("清空"), { method: "DELETE" });
  const data = await resp.json();
  alert(data.message || data.detail || "完成");
  loadStats(); loadUsage(); loadLogs();
});

/* ---------- 健康 ---------- */
async function ping() {
  try {
    const h = await (await fetch("/api/health")).json();
    const el = $("#health");
    el.textContent = `● 正常 · 端口：${h.recognizer}`;
    el.classList.add("on");
  } catch { $("#health").textContent = "○ 服务未连接"; }
}

function fmtBytes(n) {
  if (n < 1024) return n + " B";
  if (n < 1048576) return (n / 1024).toFixed(1) + " KB";
  return (n / 1048576).toFixed(2) + " MB";
}
function escapeHtml(s) {
  return String(s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}

ping(); loadConfig(); loadStats(); loadUsage(); loadLogs();
