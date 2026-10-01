(() => {
  if (window.__AUTOVIDEOAI_LOADED__) return;
  window.__AUTOVIDEOAI_LOADED__ = true;
  let lastStatus = 'Ready. Start the local bridge, then queue a scene.';

  function visible(el) {
    if (!el) return false;
    const s = getComputedStyle(el), r = el.getBoundingClientRect();
    return s.display !== 'none' && s.visibility !== 'hidden' && r.width > 2 && r.height > 2;
  }
  function norm(s){ return (s||'').replace(/\s+/g,' ').trim().toLowerCase(); }
  function text(el){ return norm(el.innerText || el.textContent || el.getAttribute?.('aria-label') || ''); }
  function all(sel){ return [...document.querySelectorAll(sel)].filter(visible); }
  function candidates(){ return all('button,[role="button"],[role="tab"],[role="option"],div[tabindex],span[tabindex]'); }
  function findTextButton(words) {
    words = Array.isArray(words) ? words : [words];
    const ws = words.map(norm);
    return candidates().find(el => ws.some(w => text(el).includes(w)));
  }
  async function clickText(words, wait=500) {
    const el = findTextButton(words);
    if (!el) return false;
    el.scrollIntoView({block:'center'}); el.click();
    await sleep(wait); return true;
  }
  function sleep(ms){ return new Promise(r=>setTimeout(r,ms)); }
  function setStatus(s){ lastStatus=s; const n=document.querySelector('#autovideoai-panel .av-status'); if(n)n.textContent=s; emit('status',{message:s,url:location.href}); }
  function emit(kind, extra={}) { try { chrome.runtime.sendMessage({type:'AUTOVIDEO_EVENT',payload:{kind,...extra}}); } catch(_){} }

  function promptBoxes() {
    const els = all('textarea,input[type="text"],[contenteditable="true"],[role="textbox"]');
    return els.filter(el => {
      const a = norm([el.getAttribute('placeholder'),el.getAttribute('aria-label'),el.getAttribute('data-placeholder')].filter(Boolean).join(' '));
      return a.includes('prompt') || a.includes('describe') || a.includes('create') || a.includes('ask') || el.tagName==='TEXTAREA' || el.getAttribute('contenteditable')==='true';
    });
  }
  function bestPromptBox(){
    const xs = promptBoxes();
    xs.sort((a,b)=> (b.getBoundingClientRect().width*b.getBoundingClientRect().height) - (a.getBoundingClientRect().width*a.getBoundingClientRect().height));
    return xs[0] || null;
  }
  function setNativeValue(el, value){
    el.focus();
    if (el.isContentEditable) {
      el.textContent = value;
      el.dispatchEvent(new InputEvent('input',{bubbles:true,inputType:'insertText',data:value}));
    } else {
      const proto = el.tagName==='TEXTAREA' ? HTMLTextAreaElement.prototype : HTMLInputElement.prototype;
      const setter = Object.getOwnPropertyDescriptor(proto,'value')?.set;
      if (setter) setter.call(el,value); else el.value=value;
      el.dispatchEvent(new Event('input',{bubbles:true}));
      el.dispatchEvent(new Event('change',{bubbles:true}));
    }
  }
  async function selectAspect(aspect){
    if (!aspect) return false;
    if (await clickText([aspect],300)) return true;
    const labels = aspect==='9:16' ? ['portrait','vertical'] : ['landscape','horizontal'];
    return clickText(labels,300);
  }
  async function selectModel(hint){
    if (!hint) return false;
    const modelBtn = findTextButton(['veo','omni','model']);
    if (modelBtn) { modelBtn.click(); await sleep(350); }
    return clickText([hint],400);
  }
  async function enterPrompt(prompt){
    for(let i=0;i<15;i++){
      const box=bestPromptBox();
      if(box){ setNativeValue(box,prompt); await sleep(300); return true; }
      await sleep(700);
    }
    return false;
  }
  async function clickGenerate(){
    for(let i=0;i<10;i++){
      const b=findTextButton(['generate','create']);
      if(b && !b.disabled && b.getAttribute('aria-disabled')!=='true'){ b.click(); return true; }
      await sleep(500);
    }
    return false;
  }
  function pageSignals(){
    const t=norm(document.body?.innerText || '');
    return {
      login: t.includes('sign in') || t.includes('log in'),
      quota: t.includes('out of credits') || t.includes('not enough credits') || t.includes('credit limit') || t.includes('quota'),
      error: t.includes('something went wrong') || t.includes("couldn't generate") || t.includes('generation failed'),
      generating: t.includes('generating') || t.includes('creating') || t.includes('in progress')
    };
  }
  async function runScene(task){
    const p=task.payload||{};
    setStatus(`Scene ${task.id}: preparing Flow…`);
    const sig0=pageSignals();
    if(sig0.login) return {ok:false,needs_user:true,reason:'Google login is required in this Chrome tab.'};
    if(sig0.quota) return {ok:false,needs_user:true,reason:'Flow reports insufficient credits/quota.'};
    // Best-effort mode selection; redesigned Flow may already be in the correct create canvas.
    await clickText(['video'],250);
    await selectAspect(p.aspect || '9:16');
    await selectModel(p.model_hint || '');
    const entered=await enterPrompt(p.prompt || '');
    if(!entered){
      setStatus('Could not locate Flow prompt box. Open a Create/Video canvas and click Retry.');
      return {ok:false,needs_user:true,reason:'prompt_box_not_found',debug:{url:location.href,buttons:candidates().slice(0,40).map(text)}};
    }
    if(p.auto_generate===false){
      setStatus('Prompt inserted. Review it in Flow, then click Generate manually.');
      return {ok:true,assisted:true,stage:'prompt_inserted'};
    }
    const generated=await clickGenerate();
    if(!generated){
      setStatus('Prompt inserted, but Generate was not found. Click Generate manually.');
      return {ok:true,assisted:true,stage:'prompt_inserted_generate_missing'};
    }
    setStatus('Generation started in Flow. AutoVideoAI is leaving the tab open for review/download.');
    return {ok:true,stage:'generation_started'};
  }

  chrome.runtime.onMessage.addListener((msg, sender, sendResponse) => {
    if(msg?.type!=='AUTOVIDEO_TASK') return;
    runScene(msg.task).then(sendResponse).catch(e=>sendResponse({ok:false,error:String(e)}));
    return true;
  });

  const panel=document.createElement('div');
  panel.id='autovideoai-panel';
  panel.innerHTML='<div class="av-title">🎬 AutoVideoAI Flow Companion</div><div class="av-status"></div><button class="av-secondary" id="av-hide">Hide</button>';
  document.documentElement.appendChild(panel);
  panel.querySelector('.av-status').textContent=lastStatus;
  panel.querySelector('#av-hide').onclick=()=>panel.remove();
  emit('content_ready',{url:location.href});
})();
