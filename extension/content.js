/**
 * IDM Clone Content Script
 * - Adds "用IDM Clone下载" button on video pages
 * - Intercepts right-click on links/videos
 */

(function () {
  "use strict";

  let videoButtonAdded = false;

  // Listen for message from background
  chrome.runtime.onMessage.addListener((msg) => {
    if (msg.type === "VIDEO_PAGE_DETECTED" && !videoButtonAdded) {
      injectVideoButton(msg.url);
    }
  });

  function injectVideoButton(pageUrl) {
    if (videoButtonAdded) return;
    videoButtonAdded = true;

    const btn = document.createElement("div");
    btn.id = "idmclone-btn";
    btn.innerHTML = `
      <div style="
        position: fixed;
        bottom: 80px;
        right: 20px;
        z-index: 2147483647;
        background: #0d6efd;
        color: white;
        padding: 10px 16px;
        border-radius: 8px;
        font-family: system-ui, sans-serif;
        font-size: 13px;
        font-weight: 600;
        cursor: pointer;
        box-shadow: 0 4px 12px rgba(0,0,0,0.3);
        user-select: none;
        display: flex;
        align-items: center;
        gap: 6px;
        transition: transform 0.1s;
      " id="idmclone-inner">
        ⬇ IDM Clone 下载此视频
      </div>
    `;

    const inner = btn.querySelector("#idmclone-inner");
    inner.addEventListener("mouseenter", () => inner.style.transform = "scale(1.05)");
    inner.addEventListener("mouseleave", () => inner.style.transform = "scale(1)");
    inner.addEventListener("click", () => {
      chrome.runtime.sendMessage({ type: "SEND_VIDEO_URL", url: pageUrl });
      inner.textContent = "✓ 已发送到下载器";
      inner.style.background = "#198754";
      setTimeout(() => btn.remove(), 2000);
    });

    document.body.appendChild(btn);

    // Auto-remove after 15s if user doesn't click
    setTimeout(() => {
      if (document.contains(btn)) btn.remove();
    }, 15000);
  }

  // Right-click context menu support (via link detection)
  document.addEventListener("contextmenu", (e) => {
    const target = e.target.closest("a[href], video, audio");
    if (!target) return;
    // Store the element for context menu handler
    window.__idmclone_last_target = target;
  });
})();
