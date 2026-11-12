/* Captures a privacy-limited snapshot of the visible page and forwards it to
 * the extension service worker. Runs only in the top frame; sends nothing when
 * the tab is hidden.
 */
(function () {
  if (window.top !== window) return;

  const MAX_CHARS = 1200;

  function viewportText() {
    const out = [];
    let total = 0;
    let visited = 0;
    const vh = window.innerHeight || 800;
    if (!document.body) return '';
    const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
    let node = walker.nextNode();
    while (node && visited < 3000 && total < MAX_CHARS) {
      visited += 1;
      const current = node;
      node = walker.nextNode();
      const text = (current.nodeValue || '').trim();
      if (!text) continue;
      const parent = current.parentElement;
      if (!parent) continue;
      const tag = parent.tagName;
      if (tag === 'SCRIPT' || tag === 'STYLE' || tag === 'NOSCRIPT' || tag === 'TEMPLATE') {
        continue;
      }
      const rect = parent.getBoundingClientRect();
      if (rect.bottom < 0 || rect.top > vh || rect.width === 0) continue;
      out.push(text.slice(0, 120));
      total += text.length;
    }
    return out.join(' ').slice(0, MAX_CHARS);
  }

  function snapshot() {
    let selection = '';
    try {
      selection = window.getSelection ? String(window.getSelection()) : '';
    } catch (err) {
      selection = '';
    }
    return {
      url: location.href,
      title: document.title || '',
      visible_text: viewportText(),
      selection: selection.slice(0, 300),
    };
  }

  let lastSent = 0;
  function send(force) {
    if (document.hidden && !force) return;
    const now = Date.now();
    if (!force && now - lastSent < 4000) return;
    lastSent = now;
    try {
      chrome.runtime.sendMessage({ type: 'wt-pulse', data: snapshot() });
    } catch (err) {
      /* service worker may be restarting; next tick retries */
    }
  }

  document.addEventListener('visibilitychange', function () {
    if (!document.hidden) send(true);
  });
  window.addEventListener('focus', function () {
    send(true);
  });
  window.addEventListener('scroll', function () {
    send(false);
  }, { passive: true });
  setInterval(function () {
    send(false);
  }, 5000);
  send(true);
})();
