# Chrome Manifest V3 Browser Automation Extension Guide

## Overview

The Virtual Mouse Chrome Extension connects Google Chrome to the Virtual Mouse desktop runtime via a safe, isolated loopback bridge (`http://127.0.0.1:8765`).

## Security Design

1. **Loopback Only**: Server binds strictly to `127.0.0.1` — never accessible over LAN or WAN interfaces.
2. **Per-Session Auth Token**: Generated on application launch (`X-Bridge-Token`) to prevent rogue local apps from injecting commands.
3. **No Web Page Injection**: The extension interacts exclusively with tabs through Chrome Extension APIs (`chrome.tabs`, `chrome.windows`) and sandboxed content scripts.
4. **Organic Search Extraction**: Content script queries the DOM for organic search links while discarding ad containers (`google.com/aclk`, `duckduckgo.com/y.js`).

---

## Installation Steps (Developer Mode)

1. Open Google Chrome.
2. Navigate to `chrome://extensions/`.
3. Enable **Developer mode** using the toggle switch in the top-right corner.
4. Click **Load unpacked** in the top-left toolbar.
5. Select the `browser_extension` directory in the repository:
   ```
   VirtualMouse/browser_extension/
   ```
6. The extension **"Virtual Mouse Browser Controller"** (version 1.0.0) will appear in the installed list with background service worker registered.

---

## Chrome Manifest V3 Structure

```
browser_extension/
├── manifest.json                  # MV3 metadata, permissions, content script patterns
├── service_worker.js              # Background polling loop & tab execution engine
└── content_scripts/
    └── search_extractor.js        # Organic search result DOM extractor
```

---

## Extension Permissions

The extension requests only the minimum necessary Chrome permissions:
- `tabs`: Querying active tabs, updating tab URLs, creating new tabs, closing tabs.
- `scripting`: Executing content scripts for organic search extraction on search engines.
- `host_permissions`:
  - `http://127.0.0.1:8765/*`: Communicating with local loopback bridge.
  - `https://www.google.com/*`: Search result analysis.
  - `https://duckduckgo.com/*`: Search result analysis.

---

## End-to-End Validation Workflow

1. Start Virtual Mouse with voice mode:
   ```bash
   virtual-mouse
   ```
2. Press `v` (Voice enabled) and `m` (Master arm).
3. Say or test:
   - *"open new tab"* -> Chrome opens `https://www.google.com`.
   - *"python machine learning"* -> Google searches the query.
   - *"open first result"* -> Navigates to the first organic article, bypassing search ads.
   - *"close current tab"* -> Safely closes the active tab.
