/**
 * IDM Clone Extension Popup
 */

const DOWNLOADER_URL = "http://127.0.0.1:16800";

async function checkStatus() {
  const dot = document.getElementById("statusDot");
  const label = document.getElementById("statusLabel");
  const banner = document.getElementById("offlineBanner");

  try {
    const resp = await fetch(`${DOWNLOADER_URL}/ping`, { signal: AbortSignal.timeout(2000) });
    if (resp.ok) {
      dot.classList.add("online");
      label.textContent = "已连接";
      banner.classList.remove("visible");
      return true;
    }
  } catch {}
  dot.classList.remove("online");
  label.textContent = "未连接";
  banner.classList.add("visible");
  return false;
}

async function loadStats() {
  try {
    const resp = await fetch(`${DOWNLOADER_URL}/status`, { signal: AbortSignal.timeout(2000) });
    if (!resp.ok) return;
    const data = await resp.json();
    const stats = data.stats || {};
    document.getElementById("statActive").textContent = stats.active ?? "0";
    document.getElementById("statQueued").textContent = stats.queued ?? "0";
    document.getElementById("statDone").textContent = stats.completed ?? "0";

    // Task list
    const tasks = data.tasks || [];
    const list = document.getElementById("taskList");
    if (tasks.length === 0) {
      list.innerHTML = '<div style="color:#adb5bd;font-size:12px;text-align:center;padding:12px 0">暂无任务</div>';
      return;
    }
    list.innerHTML = tasks.slice(-5).reverse().map(t => {
      const statusColors = {
        downloading: "#0d6efd",
        completed: "#198754",
        error: "#dc3545",
        paused: "#fd7e14",
        queued: "#6c757d",
        merging: "#6f42c1"
      };
      const color = statusColors[t.status] || "#6c757d";
      const progress = t.progress || 0;
      return `
        <div class="task-item">
          <div class="task-name" title="${t.filename}">${t.filename}</div>
          <div class="task-bar"><div class="task-bar-fill" style="width:${progress}%;background:${color}"></div></div>
          <div class="task-progress" style="color:${color}">${progress}%</div>
        </div>
      `;
    }).join("");
  } catch {}
}

// Manual download
document.getElementById("btnDownload").addEventListener("click", async () => {
  const url = document.getElementById("urlInput").value.trim();
  if (!url) return;
  const btn = document.getElementById("btnDownload");
  btn.textContent = "发送中...";
  try {
    const resp = await fetch(`${DOWNLOADER_URL}/add`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ url, size: 0 }),
      signal: AbortSignal.timeout(4000)
    });
    if (resp.ok) {
      const data = await resp.json();
      btn.textContent = data.captured ? "✓ 已添加" : `跳过: ${data.reason || "过滤规则"}`;
      btn.style.background = data.captured ? "#198754" : "#6c757d";
      setTimeout(() => {
        btn.textContent = "⬇ 发送到下载器";
        btn.style.background = "";
      }, 2000);
      document.getElementById("urlInput").value = "";
      loadStats();
    }
  } catch {
    btn.textContent = "失败: 下载器未运行";
    btn.style.background = "#dc3545";
    setTimeout(() => {
      btn.textContent = "⬇ 发送到下载器";
      btn.style.background = "";
    }, 2000);
  }
});

// Video sniff button
document.getElementById("btnSniff").addEventListener("click", async () => {
  const url = document.getElementById("urlInput").value.trim();
  const activeTabUrl = await getActiveTabUrl();
  const targetUrl = url || activeTabUrl;
  if (!targetUrl) return;

  const btn = document.getElementById("btnSniff");
  btn.textContent = "嗅探中...";
  try {
    const resp = await fetch(`${DOWNLOADER_URL}/add_video`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ url: targetUrl }),
      signal: AbortSignal.timeout(4000)
    });
    if (resp.ok) {
      btn.textContent = "✓ 已发送";
      btn.style.background = "#198754";
    }
  } catch {
    btn.textContent = "失败";
    btn.style.background = "#dc3545";
  }
  setTimeout(() => {
    btn.textContent = "🔍 嗅探";
    btn.style.background = "";
  }, 2000);
});

async function getActiveTabUrl() {
  try {
    const tabs = await chrome.tabs.query({ active: true, currentWindow: true });
    return tabs[0]?.url || "";
  } catch { return ""; }
}

// Sync config
document.getElementById("btnSync").addEventListener("click", async () => {
  await chrome.runtime.sendMessage({ type: "SYNC_CONFIG" });
  document.getElementById("btnSync").textContent = "✓ 已同步";
  setTimeout(() => document.getElementById("btnSync").textContent = "🔄 同步配置", 1500);
});

// Min size change
document.getElementById("minSize").addEventListener("change", (e) => {
  const val = parseFloat(e.target.value) || 0;
  chrome.storage.local.set({ override_min_size_mb: val });
  // Also send to background to sync
  chrome.runtime.sendMessage({ type: "SYNC_CONFIG" });
});

// Init
(async () => {
  const online = await checkStatus();
  if (online) {
    await loadStats();
  }
  // Load saved min size
  const stored = await chrome.storage.local.get(["override_min_size_mb", "filterConfig"]);
  if (stored.override_min_size_mb !== undefined) {
    document.getElementById("minSize").value = stored.override_min_size_mb;
  } else if (stored.filterConfig?.min_size_mb !== undefined) {
    document.getElementById("minSize").value = stored.filterConfig.min_size_mb;
  }
})();

// Refresh every 2s while popup open
setInterval(async () => {
  const online = await checkStatus();
  if (online) loadStats();
}, 2000);
