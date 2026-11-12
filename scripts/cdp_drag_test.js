import { setTimeout as sleep } from 'node:timers/promises';
const debugPort = 9222;
const targets = await (await fetch(`http://127.0.0.1:${debugPort}/json`)).json();
const page = targets.find(t => t.type === 'page' && t.url.includes('18749'));
if (!page) { console.error('page target not found', targets.map(t=>t.url)); process.exit(1); }
const ws = new WebSocket(page.webSocketDebuggerUrl);
let seq = 0; const pending = new Map();
ws.onmessage = (ev) => { const m = JSON.parse(ev.data); if (m.id && pending.has(m.id)) { pending.get(m.id)(m); pending.delete(m.id); } };
const send = (method, params = {}) => new Promise((res) => { const i = ++seq; pending.set(i, res); ws.send(JSON.stringify({ id: i, method, params })); });
await new Promise((res) => { ws.onopen = res; });
await send('Runtime.enable');
await sleep(2500);
const before = await (await fetch('http://127.0.0.1:18749/api/day?date=2026-11-16')).json();
const rect = await send('Runtime.evaluate', { expression: `(() => { const b = document.querySelector('.block'); if (!b) return 'none'; const r = b.getBoundingClientRect(); return JSON.stringify({ id: Number(b.dataset.id), x: r.x + r.width / 2, y: r.y + r.height / 2 }); })()`, returnByValue: true });
const pos = JSON.parse(rect.result.result.value);
const seg = before.segments.find((s) => s.id === pos.id);
console.log('drag block', pos, 'before', seg.start_ts, '->', seg.end_ts);
await send('Input.dispatchMouseEvent', { type: 'mousePressed', x: pos.x, y: pos.y, button: 'left', clickCount: 1 });
for (const dx of [15, 35, 55, 75]) {
  await send('Input.dispatchMouseEvent', { type: 'mouseMoved', x: pos.x + dx, y: pos.y, button: 'left', buttons: 1 });
  await sleep(80);
}
await send('Input.dispatchMouseEvent', { type: 'mouseReleased', x: pos.x + 75, y: pos.y, button: 'left', clickCount: 1 });
await sleep(2000);
const after = await (await fetch('http://127.0.0.1:18749/api/day?date=2026-11-16')).json();
const seg2 = after.segments.find((s) => s.id === pos.id);
console.log('after', seg2.start_ts, '->', seg2.end_ts, 'duration', seg2.duration_s);
console.log(seg.start_ts !== seg2.start_ts ? 'DRAG_OK' : 'DRAG_UNCHANGED');
ws.close();
