/* WorkTime extension background worker.
 *
 * Receives page snapshots from the content script and POSTs them to the local
 * collector at http://127.0.0.1:<port>/api/event. No other network access.
 * Works identically in Chrome and Edge (same MV3 API surface).
 */

const DEFAULTS = {
  token: '',
  port: 18731,
  enabled: true,
  denylist: '',
  sendTitle: true,
  sendUrl: true,
  sendPageText: true,
  sendSelection: true,
};

let lastStatus = { ok: null, at: 0, error: '' };

async function getSettings() {
  return await chrome.storage.local.get(DEFAULTS);
}

function isHttp(url) {
  return typeof url === 'string' && /^https?:\/\//i.test(url);
}

function isDenied(url, denylist) {
  if (!isHttp(url)) return true;
  const list = String(denylist || '')
    .split(/[\s,]+/)
    .map((s) => s.trim().toLowerCase())
    .filter(Boolean);
  const lower = url.toLowerCase();
  return list.some((host) => lower.includes(host));
}

function browserName() {
  const ua = navigator.userAgent;
  if (/Edg\//.test(ua)) return 'Edge';
  if (/Chrome\//.test(ua)) return 'Chrome';
  if (/Firefox\//.test(ua)) return 'Firefox';
  return 'Browser';
}

async function postEvent(data, tabUrl) {
  const settings = await getSettings();
  if (!settings.enabled) return;
  const url = data.url || tabUrl || '';
  if (isDenied(url, settings.denylist)) return;
  const payload = {
    browser: browserName(),
    url: settings.sendUrl === false ? '' : url,
    page_title: settings.sendTitle === false ? '' : String(data.title || '').slice(0, 512),
    visible_text: settings.sendPageText === false ? '' : String(data.visible_text || '').slice(0, 1500),
    selection: settings.sendSelection === false ? '' : String(data.selection || '').slice(0, 500),
    ts: new Date().toISOString(),
  };
  try {
    const res = await fetch(`http://127.0.0.1:${settings.port}/api/event`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-WT-Token': settings.token || '',
      },
      body: JSON.stringify(payload),
    });
    lastStatus = { ok: res.ok, at: Date.now(), error: res.ok ? '' : `HTTP ${res.status}` };
  } catch (err) {
    lastStatus = { ok: false, at: Date.now(), error: String(err) };
  }
}

chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  if (!message || !message.type) return false;
  if (message.type === 'wt-pulse') {
    postEvent(message.data || {}, sender.tab ? sender.tab.url : '');
    return false;
  }
  if (message.type === 'wt-status') {
    sendResponse({ ...lastStatus });
    return true;
  }
  if (message.type === 'wt-settings') {
    getSettings().then((s) => sendResponse(s));
    return true;
  }
  return false;
});

chrome.tabs.onActivated.addListener(async (info) => {
  try {
    const tab = await chrome.tabs.get(info.tabId);
    if (tab && tab.url) {
      postEvent({ url: tab.url, title: tab.title || '' }, tab.url);
    }
  } catch (err) {
    /* ignore */
  }
});

chrome.tabs.onUpdated.addListener((tabId, changeInfo, tab) => {
  if (changeInfo.status === 'complete' && tab && tab.active && tab.url) {
    postEvent({ url: tab.url, title: tab.title || '' }, tab.url);
  }
});

try {
  chrome.alarms.create('wt-keepalive', { periodInMinutes: 0.5 });
  chrome.alarms.onAlarm.addListener(() => {
    /* keeps the service worker warm; content script drives real sampling */
  });
} catch (err) {
  /* alarms unavailable is fine */
}
