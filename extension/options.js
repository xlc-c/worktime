/* Settings page logic. */
const DEFAULTS = {
  token: '', port: 18731, enabled: true, denylist: '',
  sendTitle: true, sendUrl: true, sendPageText: true, sendSelection: true,
};

async function load() {
  const s = await chrome.storage.local.get(DEFAULTS);
  document.getElementById('token').value = s.token || '';
  document.getElementById('port').value = s.port || 18731;
  document.getElementById('denylist').value = s.denylist || '';
  document.getElementById('sendTitle').checked = s.sendTitle !== false;
  document.getElementById('sendUrl').checked = s.sendUrl !== false;
  document.getElementById('sendPageText').checked = s.sendPageText !== false;
  document.getElementById('sendSelection').checked = s.sendSelection !== false;
}

document.getElementById('save').addEventListener('click', async function () {
  const token = document.getElementById('token').value.trim();
  const port = parseInt(document.getElementById('port').value, 10) || 18731;
  const denylist = document.getElementById('denylist').value;
  await chrome.storage.local.set({
    token: token,
    port: port,
    denylist: denylist,
    enabled: true,
    sendTitle: document.getElementById('sendTitle').checked,
    sendUrl: document.getElementById('sendUrl').checked,
    sendPageText: document.getElementById('sendPageText').checked,
    sendSelection: document.getElementById('sendSelection').checked,
  });
  const msg = document.getElementById('msg');
  msg.textContent = '已保存。';
  setTimeout(function () { msg.textContent = ''; }, 2000);
});

load();
