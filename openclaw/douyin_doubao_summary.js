"use strict";

/**
 * douyin_doubao_summary.js
 *
 * 从最新的 search_*.json 文件中读取所有视频 URL，
 * 逐个用浏览器打开豆包，让豆包总结视频内容，
 * 把结果保存到 data/raw/doubao_summaries.json
 *
 * 输出字段：
 *   - video_url
 *   - author (博主)
 *   - title (视频标题)
 *   - doubao_summary (豆包总结的完整文本)
 *   - summary_at (时间戳)
 */

const fs = require("node:fs/promises");
const path = require("node:path");
const http = require("node:http");

const PROJECT_ROOT = process.env.OPENCLAW_PROJECT_ROOT || process.cwd();
const SEARCH_DIR = path.resolve(PROJECT_ROOT, "skills/douyin-search/search_results");
const OUTPUT_PATH = process.env.OPENCLAW_DOUBAO_OUTPUT_PATH || path.resolve(PROJECT_ROOT, "data/raw/doubao_summaries.json");
const WORKSPACE_ROOT = "C:\\Users\\Administrator\\.openclaw\\workspace";

const CDP_HTTP = "http://127.0.0.1:18800/json";

// 固定的保存字段
const SUMMARY_FIELDS = [
  "video_url",
  "author",
  "title",
  "doubao_summary",
  "summary_at"
];

/**
 * 从 search_*.json 中提取所有视频 URL（去重）
 */
async function extractVideoUrls() {
  const files = (await fs.readdir(SEARCH_DIR))
    .filter(f => f.startsWith("search_") && f.endsWith(".json"))
    .sort()
    .reverse();

  if (files.length === 0) {
    console.log("No search_*.json files found");
    return [];
  }

  const latestFile = files[0];
  console.log(`Reading: ${latestFile}`);
  const raw = await fs.readFile(path.join(SEARCH_DIR, latestFile), "utf-8");
  const data = JSON.parse(raw);

  const urls = [];
  const seen = new Set();

  for (const [keyword, items] of Object.entries(data.results || {})) {
    for (const item of items || []) {
      const url = item?.url || "";
      if (url && !seen.has(url)) {
        seen.add(url);
        urls.push({
          url,
          author: item?.author || "",
          title: item?.title || "",
          keyword
        });
      }
    }
  }

  console.log(`Extracted ${urls.length} unique video URLs`);
  return urls;
}

/**
 * 加载已有的总结结果
 */
async function loadExistingSummaries() {
  try {
    const raw = await fs.readFile(OUTPUT_PATH, "utf-8");
    const data = JSON.parse(raw);
    return Array.isArray(data?.items) ? data.items : [];
  } catch {
    return [];
  }
}

/**
 * 通过 CDP 连接到浏览器，操作豆包页面
 */
async function summarizeWithDoubao(videoInfo) {
  const { url, author, title } = videoInfo;

  try {
    // 1. 获取浏览器 WS URL
    const pages = await fetchJson(CDP_HTTP);
    let wsUrl = null;
    for (const p of pages) {
      if (p.type === "page" && p.url && p.url.startsWith("https://www.doubao.com/chat")) {
        wsUrl = p.webSocketDebuggerUrl;
        break;
      }
    }

    if (!wsUrl) {
      // 没有豆包页面，新建一个
      // 通过 CDP 新建页面
      const newPage = await fetchJson(`${CDP_HTTP}/new`, "PUT");
      if (!newPage?.webSocketDebuggerUrl) {
        throw new Error("Failed to create new page");
      }
      wsUrl = newPage.webSocketDebuggerUrl;
      // 导航到豆包
      await sendCDPCommand(wsUrl, "Page.navigate", { url: "https://www.doubao.com/chat/" });
      await sleep(5000);
    }

    // 2. 在豆包页面输入并发送
    const prompt = `帮我总结这个抖音视频的内容：${url}`;

    // 找到输入框并输入
    await sendCDPCommand(wsUrl, "Runtime.evaluate", {
      expression: `
        (() => {
          const textbox = document.querySelector('textarea, [contenteditable="true"], [contenteditable="plaintext-only"], input[type="text"]');
          if (!textbox) return 'no textbox found';
          
          // 聚焦并输入
          textbox.focus();
          
          // 使用 execCommand 或直接设置 value
          if (textbox.tagName === 'TEXTAREA' || textbox.tagName === 'INPUT') {
            textbox.value = ${JSON.stringify(prompt)};
            textbox.dispatchEvent(new Event('input', { bubbles: true }));
            textbox.dispatchEvent(new Event('change', { bubbles: true }));
          } else if (textbox.isContentEditable) {
            textbox.textContent = ${JSON.stringify(prompt)};
            textbox.dispatchEvent(new Event('input', { bubbles: true }));
          }
          
          return 'text input done';
        })()
      `
    });
    await sleep(2000);

    // 查找并点击发送按钮
    await sendCDPCommand(wsUrl, "Runtime.evaluate", {
      expression: `
        (() => {
          // 尝试多种选择器找发送按钮
          const buttons = document.querySelectorAll('button');
          for (const btn of buttons) {
            const svg = btn.querySelector('svg');
            if (svg && (btn.offsetWidth > 0 || btn.offsetHeight > 0)) {
              // 这是发送按钮（通常带 svg 图标）
              btn.click();
              return 'clicked send button';
            }
          }
          
          // 尝试按 Enter
          const textbox = document.querySelector('textarea, [contenteditable="true"]');
          if (textbox) {
            const enterEvent = new KeyboardEvent('keydown', { key: 'Enter', code: 'Enter', keyCode: 13, which: 13, bubbles: true });
            textbox.dispatchEvent(enterEvent);
            return 'sent via Enter';
          }
          
          return 'no send method found';
        })()
      `
    });

    // 3. 等待豆包生成回复
    console.log(`  Waiting for Doubao to summarize: ${url.substring(0, 50)}...`);
    await sleep(15000);

    // 4. 获取豆包回复内容
    const result = await sendCDPCommand(wsUrl, "Runtime.evaluate", {
      expression: `
        (() => {
          // 获取页面中所有文本
          const allText = document.body.innerText || '';
          
          // 找到最新一条 AI 回复（豆包回复）
          // 豆包回复通常在用户消息之后出现
          const messages = document.querySelectorAll('[class*="message"], [class*="chat"], [class*="reply"], [class*="answer"], [class*="response"]');
          let replyText = '';
          
          for (const msg of messages) {
            const text = msg.textContent.trim();
            if (text && text.length > 50 && !text.includes('发消息...') && !text.includes('快速')) {
              replyText = text;
            }
          }
          
          // 如果没找到结构化元素，就用页面正文
          if (!replyText && allText.length > 100) {
            // 找到用户消息之后的内容
            const parts = allText.split('发消息...');
            replyText = parts.length > 0 ? parts[parts.length - 1].trim() : '';
          }
          
          return JSON.stringify({
            replyText: replyText.substring(0, 5000),
            allTextLength: allText.length
          });
        })()
      `
    });

    const pageContent = JSON.parse(result?.result?.value || "{}");
    return {
      video_url: url,
      author: author || "",
      title: title || "",
      doubao_summary: pageContent.replyText || "",
      summary_at: new Date().toISOString()
    };

  } catch (err) {
    console.error(`  Error summarizing ${url}: ${err.message}`);
    return {
      video_url: url,
      author: author || "",
      title: title || "",
      doubao_summary: `[Error: ${err.message}]`,
      summary_at: new Date().toISOString()
    };
  }
}

/**
 * 通过 CDP 发送命令
 */
function sendCDPCommand(wsUrl, method, params = {}) {
  return new Promise((resolve, reject) => {
    const ws = new (require("ws"))(wsUrl);
    const id = Date.now();
    const timer = setTimeout(() => {
      ws.close();
      reject(new Error(`CDP timeout: ${method}`));
    }, 30000);

    ws.on("open", () => {
      ws.send(JSON.stringify({ id, method, params }));
    });

    ws.on("message", (data) => {
      clearTimeout(timer);
      try {
        const resp = JSON.parse(data.toString());
        if (resp.id === id) {
          ws.close();
          resolve(resp);
        }
      } catch {}
    });

    ws.on("error", (err) => {
      clearTimeout(timer);
      reject(err);
    });
  });
}

/**
 * 发送 CDP 命令并等待，支持多次 recv
 */
async function sendCDPCommandV2(wsUrl, method, params = {}, waitMs = 5000) {
  return new Promise((resolve, reject) => {
    const WebSocket = require("ws");
    const ws = new WebSocket(wsUrl);
    const id = Date.now();
    const results = [];
    const timer = setTimeout(() => {
      try { ws.close(); } catch {}
      resolve({ id, result: results, timedOut: true });
    }, waitMs);

    ws.on("open", () => {
      ws.send(JSON.stringify({ id, method, params }));
    });

    ws.on("message", (data) => {
      try {
        const resp = JSON.parse(data.toString());
        results.push(resp);
        if (resp.id === id && resp.result) {
          clearTimeout(timer);
          try { ws.close(); } catch {}
          resolve({ id, result: resp.result, timedOut: false });
        }
      } catch {}
    });

    ws.on("error", (err) => {
      clearTimeout(timer);
      reject(err);
    });
  });
}

/**
 * HTTP fetch 辅助
 */
function fetchJson(url, method = "GET") {
  return new Promise((resolve, reject) => {
    const urlObj = new URL(url);
    const options = {
      hostname: urlObj.hostname,
      port: urlObj.port,
      path: urlObj.pathname + urlObj.search,
      method,
      headers: { "Content-Type": "application/json" }
    };

    const req = http.request(options, (res) => {
      let data = "";
      res.on("data", (chunk) => data += chunk);
      res.on("end", () => {
        try { resolve(JSON.parse(data)); }
        catch { resolve(null); }
      });
    });
    req.on("error", reject);
    req.end();
  });
}

function sleep(ms) {
  return new Promise(resolve => setTimeout(resolve, ms));
}

/**
 * 主入口
 */
async function run() {
  console.log("=== Douyin → Doubao Summary Pipeline ===");

  // 1. 从 search JSON 提取视频 URL
  const videoUrls = await extractVideoUrls();
  if (videoUrls.length === 0) {
    console.log("No videos found to summarize");
    return { items: [], source: "doubao-summary", note: "no videos" };
  }

  // 2. 加载已有总结，避免重复
  const existing = await loadExistingSummaries();
  const existingUrls = new Set(existing.map(item => item.video_url));

  // 找到需要总结的新视频
  const newVideos = videoUrls.filter(v => !existingUrls.has(v.url));
  console.log(`Existing summaries: ${existing.length}, New to process: ${newVideos.length}`);

  if (newVideos.length === 0) {
    console.log("All videos already summarized");
    return { items: existing, source: "doubao-summary", exported_at: new Date().toISOString() };
  }

  // 3. 逐个总结
  const newSummaries = [];
  for (let i = 0; i < newVideos.length; i++) {
    const video = newVideos[i];
    console.log(`[${i + 1}/${newVideos.length}] Summarizing: ${video.url.substring(0, 50)}...`);
    
    const summary = await summarizeWithDoubao(video);
    newSummaries.push(summary);
    
    // 每处理一个保存一次
    const allItems = [...existing, ...newSummaries];
    await saveOutput(allItems);
    
    // 间隔，避免过快
    if (i < newVideos.length - 1) {
      await sleep(3000);
    }
  }

  // 4. 保存最终结果
  const allItems = [...existing, ...newSummaries];
  await saveOutput(allItems);

  console.log(`\nDone! Total summaries: ${allItems.length}`);
  return { items: allItems, source: "doubao-summary", exported_at: new Date().toISOString() };
}

async function saveOutput(items) {
  const output = {
    source: "doubao-summary",
    exported_at: new Date().toISOString(),
    total: items.length,
    items
  };
  await fs.mkdir(path.dirname(OUTPUT_PATH), { recursive: true });
  await fs.writeFile(OUTPUT_PATH, JSON.stringify(output, null, 2) + "\n", "utf-8");
}

if (require.main === module) {
  run()
    .then((result) => {
      console.log(`Exported ${result.items?.length || 0} summaries -> ${OUTPUT_PATH}`);
    })
    .catch((err) => {
      console.error("Fatal:", err.message);
      process.exitCode = 1;
    });
}

module.exports = { run, extractVideoUrls, loadExistingSummaries };
