#!/usr/bin/env node
/**
 * S.D. 智能财务 · 微信 ClawBot 传话筒（OpenClaw 侧脚本，Node ≥ 18，零依赖）
 *
 * 职责（对应会议共识「ClawBot 只做传话筒」）：
 *   收到微信图片 → 不做任何 AI 分析 → 原样 POST 到本地 WebApp → 把处理结果回给微信。
 *
 * 用法：
 *   node forward_to_webapp.js <图片路径或URL> [发送者标识] [文件名]
 *
 * 环境变量：
 *   SD_WEBAPP_URL   WebApp 地址，默认 http://127.0.0.1:8000
 *   SD_BOT_TOKEN    管理后台配置的 BOT_TOKEN（未配置则留空）
 *
 * 输出：stdout 打印一行要回复到微信的文本（供 OpenClaw Skill 捕获并回复）。
 * 退出码：0 = 已送达（含需复核/重复）；1 = 失败。
 */
const fs = require("node:fs");
const path = require("node:path");

const WEBAPP = (process.env.SD_WEBAPP_URL || "http://127.0.0.1:8000").replace(/\/$/, "");
const TOKEN = process.env.SD_BOT_TOKEN || "";

async function readImage(source) {
  if (/^https?:\/\//i.test(source)) {
    const resp = await fetch(source);
    if (!resp.ok) throw new Error(`下载图片失败 HTTP ${resp.status}`);
    return Buffer.from(await resp.arrayBuffer());
  }
  return fs.readFileSync(source);
}

function guessFileName(source) {
  if (/^https?:\/\//i.test(source)) {
    const p = new URL(source).pathname;
    return path.basename(p) || "wechat.jpg";
  }
  return path.basename(source);
}

async function main() {
  const [source, user = "wechat", fileNameArg] = process.argv.slice(2);
  if (!source) {
    console.log("❌ 用法：node forward_to_webapp.js <图片路径或URL> [发送者]");
    process.exit(1);
  }

  let data;
  try {
    data = await readImage(source);
  } catch (err) {
    console.log(`❌ 读取图片失败：${err.message}`);
    process.exit(1);
  }

  const fileName = fileNameArg || guessFileName(source);
  try {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), 30000);
    const resp = await fetch(`${WEBAPP}/api/bot/upload`, {
      method: "POST",
      headers: {
        "Content-Type": "application/octet-stream",
        "X-Bot-Token": TOKEN,
        "X-User": String(user),
        "X-File-Name": encodeURIComponent(fileName),
      },
      body: data,
      signal: controller.signal,
    });
    clearTimeout(timer);
    const body = await resp.json().catch(() => ({}));
    console.log(body.reply || (resp.ok ? "✅ 已同步到财务系统" : `❌ 同步失败 HTTP ${resp.status}`));
    process.exit(resp.ok ? 0 : 1);
  } catch (err) {
    const reason = err.name === "AbortError" ? "连接超时（30s）" : err.message;
    console.log(`❌ 无法连接财务系统（${WEBAPP}）：${reason}。请确认 WebApp 已启动。`);
    process.exit(1);
  }
}

main();
