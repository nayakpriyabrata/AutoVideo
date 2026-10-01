const BRIDGE = 'http://127.0.0.1:8765';
let enabled = true;
let busy = false;

async function post(path, body) {
  try {
    await fetch(BRIDGE + path, {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(body)});
  } catch (_) {}
}

async function findFlowTab() {
  const tabs = await chrome.tabs.query({url:['https://flow.google.com/*']});
  if (!tabs.length) return null;
  return tabs.find(t => /\/fx|flow/i.test(t.url || '')) || tabs[0];
}

async function tick() {
  if (!enabled || busy) return;
  let data;
  try {
    const r = await fetch(BRIDGE + '/next', {cache:'no-store'});
    if (!r.ok) return;
    data = await r.json();
  } catch (_) { return; }
  const task = data.task;
  if (!task) return;
  busy = true;
  try {
    let tab = await findFlowTab();
    if (!tab) {
      tab = await chrome.tabs.create({url:'https://flow.google.com/', active:true});
      await new Promise(r => setTimeout(r, 5000));
    }
    const result = await chrome.tabs.sendMessage(tab.id, {type:'AUTOVIDEO_TASK', task});
    await post('/result', {id:task.id, ok:!!result?.ok, result:result || null});
  } catch (e) {
    await post('/result', {id:task.id, ok:false, error:String(e)});
  } finally { busy = false; }
}
setInterval(tick, 1800);

chrome.runtime.onMessage.addListener((msg, sender, sendResponse) => {
  if (msg?.type === 'AUTOVIDEO_STATUS') {
    sendResponse({enabled, busy, bridge:BRIDGE});
    return true;
  }
  if (msg?.type === 'AUTOVIDEO_ENABLE') {
    enabled = !!msg.enabled;
    sendResponse({ok:true, enabled});
    return true;
  }
  if (msg?.type === 'AUTOVIDEO_EVENT') {
    post('/event', msg.payload || {});
    sendResponse({ok:true});
    return true;
  }
});

chrome.downloads.onChanged.addListener(async delta => {
  if (!delta.state || delta.state.current !== 'complete') return;
  try {
    const [item] = await chrome.downloads.search({id: delta.id});
    if (item) await post('/download', {id:item.id, filename:item.filename, url:item.url, mime:item.mime || ''});
  } catch (_) {}
});
