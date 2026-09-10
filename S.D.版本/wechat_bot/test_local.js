#!/usr/bin/env node
/**
 * 本地自测：不经过微信，直接模拟 ClawBot 向 WebApp 发一张测试图片。
 *
 * 用法：
 *   node test_local.js            # 无令牌测试
 *   SD_BOT_TOKEN=xxx node test_local.js
 *
 * 预期：WebApp 返回 JSON，reply 为面向用户的一句话结果。
 */
const WEBAPP = (process.env.SD_WEBAPP_URL || "http://127.0.0.1:8000").replace(/\/$/, "");
const TOKEN = process.env.SD_BOT_TOKEN || "";

// 一张 1x1 像素的合法 PNG
const PNG_1PX = Buffer.from(
  "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==",
  "base64"
);

async function main() {
  console.log(`→ POST ${WEBAPP}/api/bot/upload  (${PNG_1PX.length} bytes, token=${TOKEN ? "已带" : "未带"})`);
  try {
    const resp = await fetch(`${WEBAPP}/api/bot/upload`, {
      method: "POST",
      headers: {
        "Content-Type": "application/octet-stream",
        "X-Bot-Token": TOKEN,
        "X-User": "local-test",
        "X-File-Name": "test.png",
      },
      body: PNG_1PX,
    });
    const body = await resp.json().catch(() => ({}));
    console.log(`← HTTP ${resp.status}`);
    console.log(JSON.stringify(body, null, 2));
    if (resp.status === 403) {
      console.log("\n提示：服务端已配置 BOT_TOKEN，请用 SD_BOT_TOKEN=xxx 重试。");
    }
  } catch (err) {
    console.log(`← 连接失败：${err.message}`);
    console.log("请先启动 WebApp（双击 一键启动.bat）。");
    process.exit(1);
  }
}

main();
