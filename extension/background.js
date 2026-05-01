/**
 * IDM Clone Extension - Background Service Worker
 * Intercepts browser downloads and sends them to local downloader.
 * Also sniffs video pages for YouTube/Bilibili/Douyin.
 */

const DOWNLOADER_URL = "http://127.0.0.1:16800";

// Default filter config (synced from downloader)
let filterConfig = {
  captured_types: [
    "zip","rar","7z","tar","gz","bz2",
    "exe","msi","dmg","pkg","deb","rpm",
    "mp4","mkv","avi","mov","wmv","flv","webm",
    "mp3","flac","wav","aac","ogg",
    "pdf","doc","docx","xls","xlsx","ppt","pptx",
    "iso","img","bin"
  ],
  min_size_mb: 1,
  site_blacklist: []
};

// Video site patterns for page-level sniffing
const VIDEO_SITE_PATTERNS = [
  /youtube\.com\/watch/i,
  /youtu\.be\//i,
  /bilibili\.com\/video/i,
  /douyin\.com/i,
  /iqdouyin\.com/i,
  /tiktok\.com/i,
  /twitter\.com.*\/video/i,
  /x\.com.*\/video/i,
  /instagram\.com\/p\//i,
  /vimeo\.com\/\d+/i,
];

// ── Startup ────────────────────────────────────────────────────────────
chrome.runtime.onInstalled.addListener(() => {
  console.log("[IDMClone] Extension installed");
  syncConfigFromDownloader();
});

chrome.runtime.onStartup.addListener(() => {
  syncConfigFromDownloader();
});

// Sync filter config from downloader every 60s
setInterval(syncConfigFromDownloader, 60000);

async function syncConfigFromDownloader() {
  try {
    const resp = await fetch(`${DOWNLOADER_URL}/config`, { signal: AbortSignal.timeout(3000) });
    if (resp.ok) {
      const cfg = await resp.json();
      filterConfig = { ...filterConfig, ...cfg };
      await chrome.storage.local.set({ filterConfig, downloaderOnline: true });
    }
  } catch {
    await chrome.storage.local.set({ downloaderOnline: false });
  }
}

// ── Download Interception ──────────────────────────────────────────────
chrome.downloads.onCreated.addListener(async (item) => {
  const url = item.url || item.finalUrl || "";
  if (!url || url.startsWith("blob:") || url.startsWith("data:")) return;

  const filename = item.filename ? item.filename.split(/[\\/]/).pop() : guessFilename(url);
  const ext = getExt(filename);
  const host = getHost(url);
  const sizeBytes = item.fileSize || 0;

  if (!shouldCapture(ext, host, sizeBytes)) return;

  // Cancel browser download
  try {
    await chrome.downloads.cancel(item.id);
    await chrome.downloads.erase({ id: item.id });
  } catch (e) {
    console.warn("[IDMClone] Could not cancel download:", e);
  }

  // Send to downloader
  const tab = await getActiveTab();
  const referrer = tab?.url || "";
  const cookies = await getTabCookies(url);

  const payload = {
    url,
    filename,
    size: sizeBytes,
    referrer,
    cookies,
    site: host,
    content_disposition: item.mime || ""
  };

  const ok = await sendToDownloader("/add", payload);
  if (ok) {
    showNotification(`已发送到 IDM Clone`, filename);
  } else {
    // Downloader offline - let browser handle it
    chrome.downloads.download({ url });
  }
});

// ── Tab Navigation - Video Sniffing ───────────────────────────────────
chrome.tabs.onUpdated.addListener(async (tabId, changeInfo, tab) => {
  if (changeInfo.status !== "complete") return;
  const url = tab.url || "";
  if (isVideoPage(url)) {
    // Inject sniff hint to content script
    try {
      await chrome.tabs.sendMessage(tabId, { type: "VIDEO_PAGE_DETECTED", url });
    } catch {
      // Content script may not be ready yet, that's ok
    }
  }
});

// ── Message Handling (from content script / popup) ─────────────────────
chrome.runtime.onMessage.addListener((msg, sender, sendResponse) => {
  if (msg.type === "SEND_VIDEO_URL") {
    sendToDownloader("/add_video", { url: msg.url })
      .then(ok => sendResponse({ ok }));
    return true;
  }

  if (msg.type === "SEND_DOWNLOAD_URL") {
    sendToDownloader("/add", {
      url: msg.url,
      filename: guessFilename(msg.url),
      referrer: msg.referrer || "",
      size: 0
    }).then(ok => sendResponse({ ok }));
    return true;
  }

  if (msg.type === "CHECK_STATUS") {
    fetch(`${DOWNLOADER_URL}/ping`, { signal: AbortSignal.timeout(2000) })
      .then(r => r.ok ? r.json() : null)
      .then(data => sendResponse({ online: !!data }))
      .catch(() => sendResponse({ online: false }));
    return true;
  }

  if (msg.type === "GET_CONFIG") {
    sendResponse({ config: filterConfig });
  }

  if (msg.type === "SYNC_CONFIG") {
    syncConfigFromDownloader().then(() => sendResponse({ ok: true }));
    return true;
  }
});

// ── Helpers ────────────────────────────────────────────────────────────
function shouldCapture(ext, host, sizeBytes) {
  // Site blacklist
  const blacklist = filterConfig.site_blacklist || [];
  for (const blocked of blacklist) {
    if (host === blocked || host.endsWith("." + blocked)) return false;
  }

  // File type filter
  const types = filterConfig.captured_types || [];
  if (types.length > 0 && ext && !types.includes(ext.toLowerCase())) return false;

  // Min size (only if server reports actual size)
  const minBytes = (filterConfig.min_size_mb || 0) * 1024 * 1024;
  if (minBytes > 0 && sizeBytes > 0 && sizeBytes < minBytes) return false;

  return true;
}

function isVideoPage(url) {
  return VIDEO_SITE_PATTERNS.some(p => p.test(url));
}

function getExt(filename) {
  if (!filename) return "";
  const parts = filename.split(".");
  return parts.length > 1 ? parts.pop().toLowerCase() : "";
}

function getHost(url) {
  try { return new URL(url).hostname.replace(/^www\./, ""); }
  catch { return ""; }
}

function guessFilename(url) {
  try {
    const path = new URL(url).pathname;
    const name = path.split("/").pop();
    return decodeURIComponent(name || "download");
  } catch { return "download"; }
}

async function getActiveTab() {
  try {
    const tabs = await chrome.tabs.query({ active: true, currentWindow: true });
    return tabs[0] || null;
  } catch { return null; }
}

async function getTabCookies(url) {
  try {
    const cookies = await chrome.cookies.getAll({ url });
    return cookies.map(c => `${c.name}=${c.value}`).join("; ");
  } catch { return ""; }
}

async function sendToDownloader(path, payload) {
  try {
    const resp = await fetch(`${DOWNLOADER_URL}${path}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
      signal: AbortSignal.timeout(5000)
    });
    return resp.ok;
  } catch {
    return false;
  }
}

function showNotification(title, message) {
  chrome.notifications.create({
    type: "basic",
    iconUrl: "icons/icon48.png",
    title,
    message: message.substring(0, 100),
    silent: true
  });
}
