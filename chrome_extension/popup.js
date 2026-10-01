const s=document.getElementById('s'), b=document.getElementById('toggle');
chrome.runtime.sendMessage({type:'AUTOVIDEO_STATUS'}, r=>{if(!r){s.textContent='Extension service worker unavailable.';return;} s.textContent=`Bridge: ${r.bridge}\n${r.busy?'Busy with a scene':'Ready'}\n${r.enabled?'Enabled':'Disabled'}`; b.textContent=r.enabled?'Disable':'Enable'; b.dataset.enabled=String(r.enabled)});
b.onclick=()=>{const enabled=b.dataset.enabled!=='true'; chrome.runtime.sendMessage({type:'AUTOVIDEO_ENABLE',enabled},()=>location.reload())};
