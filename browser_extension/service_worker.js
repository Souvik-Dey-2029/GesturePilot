// Chrome Manifest V3 Background Service Worker
const BRIDGE_URL = "http://127.0.0.1:8765/api/command";

// Command Executor
async function handleCommand(cmd) {
  const { action, payload } = cmd;

  if (action === "browser.new_tab") {
    const tab = await chrome.tabs.create({ url: "https://www.google.com" });
    return { success: true, tabId: tab.id };
  }

  if (action === "browser.search") {
    const query = encodeURIComponent(payload.query || "");
    const searchUrl = `https://www.google.com/search?q=${query}`;
    const tabs = await chrome.tabs.query({ active: true, currentWindow: true });
    if (tabs.length > 0) {
      await chrome.tabs.update(tabs[0].id, { url: searchUrl });
      return { success: true, tabId: tabs[0].id, url: searchUrl };
    } else {
      const tab = await chrome.tabs.create({ url: searchUrl });
      return { success: true, tabId: tab.id, url: searchUrl };
    }
  }

  if (action === "browser.switch_tab") {
    const query = (payload.query || "").toLowerCase();
    const tabs = await chrome.tabs.query({});
    const matched = tabs.find(t => (t.title && t.title.toLowerCase().includes(query)) || (t.url && t.url.toLowerCase().includes(query)));
    if (matched) {
      await chrome.tabs.update(matched.id, { active: true });
      if (matched.windowId) {
        await chrome.windows.update(matched.windowId, { focused: true });
      }
      return { success: true, tabId: matched.id, title: matched.title };
    }
    return { success: false, error: "Tab not found" };
  }

  if (action === "browser.close_tab") {
    const query = (payload.query || "").toLowerCase();
    if (query === "current" || !query) {
      const tabs = await chrome.tabs.query({ active: true, currentWindow: true });
      if (tabs.length > 0) {
        await chrome.tabs.remove(tabs[0].id);
        return { success: true, closedTabId: tabs[0].id };
      }
    } else {
      const tabs = await chrome.tabs.query({});
      const matched = tabs.find(t => (t.title && t.title.toLowerCase().includes(query)) || (t.url && t.url.toLowerCase().includes(query)));
      if (matched) {
        await chrome.tabs.remove(matched.id);
        return { success: true, closedTabId: matched.id, title: matched.title };
      }
    }
    return { success: false, error: "Tab not found to close" };
  }

  if (action === "browser.open_first_result") {
    const tabs = await chrome.tabs.query({ active: true, currentWindow: true });
    if (tabs.length > 0) {
      try {
        const response = await chrome.tabs.sendMessage(tabs[0].id, { action: "extract_first_result" });
        if (response && response.url) {
          await chrome.tabs.update(tabs[0].id, { url: response.url });
          return { success: true, openedUrl: response.url, title: response.title };
        }
      } catch (err) {
        return { success: false, error: "Content script unavailable on this page" };
      }
    }
    return { success: false, error: "No active search page found" };
  }

  return { success: false, error: "Unknown browser action" };
}

// Local polling loop to receive commands securely from Python loopback bridge
async function pollLoop() {
  try {
    const resp = await fetch("http://127.0.0.1:8765/api/poll");
    if (resp.ok) {
      const data = await resp.json();
      if (data && data.command) {
        const result = await handleCommand(data.command);
        await fetch("http://127.0.0.1:8765/api/result", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ id: data.id, result })
        });
      }
    }
  } catch (e) {
    // Bridge server may be offline when mouse is not running
  }
  setTimeout(pollLoop, 250);
}

pollLoop();
