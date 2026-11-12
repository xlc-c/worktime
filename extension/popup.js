/* Popup: show whether events reach the local collector. */
async function refresh() {
  const statusEl = document.getElementById('status');
  try {
    const res = await chrome.runtime.sendMessage({ type: 'wt-status' });
    if (!res || res.ok === null) {
      statusEl.textContent = '未收到上报';
      statusEl.className = '';
    } else if (res.ok) {
      statusEl.textContent = '正常';
      statusEl.className = 'ok';
    } else {
      statusEl.textContent = '失败';
      statusEl.className = 'bad';
    }
    document.getElementById('last').textContent = res && res.at
      ? new Date(res.at).toLocaleTimeString()
      : '-';
    document.getElementById('error').textContent = (res && res.error) || '-';
  } catch (err) {
    statusEl.textContent = '未知';
  }
}

document.getElementById('options').addEventListener('click', function () {
  chrome.runtime.openOptionsPage();
});

refresh();
setInterval(refresh, 2000);
