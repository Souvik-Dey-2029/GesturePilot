// Content script to identify organic search results, excluding sponsored ads and malformed URLs
(function() {
  function getFirstOrganicResult() {
    const isGoogle = window.location.hostname.includes("google");
    const isDDG = window.location.hostname.includes("duckduckgo");

    if (isGoogle) {
      // Find main search container (avoiding top ads container)
      const searchContainer = document.querySelector("#search, #rso");
      if (!searchContainer) return null;

      // Select organic result link headers
      const candidates = searchContainer.querySelectorAll("div.g a, div[data-hveid] a");
      for (const a of candidates) {
        const href = a.href;
        // Exclude internal Google links and ads
        if (href && href.startsWith("http") && !href.includes("google.com") && !href.includes("/aclk?")) {
          const title = a.innerText.trim() || a.getAttribute("aria-label") || href;
          return { title, url: href, organic: true };
        }
      }
    } else if (isDDG) {
      const candidates = document.querySelectorAll("article h2 a, a[data-testid='result-title-a']");
      for (const a of candidates) {
        if (a.href && !a.href.includes("duckduckgo.com/y.js")) {
          return { title: a.innerText.trim(), url: a.href, organic: true };
        }
      }
    }
    return null;
  }

  // Listen for extraction requests from background service worker
  chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
    if (message.action === "extract_first_result") {
      const res = getFirstOrganicResult();
      sendResponse(res);
    }
  });
})();
