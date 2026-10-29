/* PULSE ARENA 3 — touch-first performance surface. No external dependencies. */
(()=>{'use strict';
const $=id=>document.getElementById(id), mk=(tag,cls,txt)=>{const x=document.createElement(tag);if(cls)x.className=cls;if(txt!==undefined)x.textContent=txt;return x};
const storage={get(k,d){try{return JSON.parse(localStorage.getItem('pulse3_'+k))??d}catch{return d}},set(k,v){localStorage.setItem('pulse3_'+k,JSON.stringify(v))}};
const S={live:true,authed:false,online:false,source:'demo',comp:null,preset:{version:3,name:'My Show',pads:{},fx:{}},cfg:null,
    deck:1,group:1,layer:2,layerOffset:0,colOffset:0,pageSize:storage.get('columns',window.innerWidth<=1000?8:10),rowSize:storage.get('layers',8),
    dockVisible:true,selectedPad:null,editingFx:null,fxStates:{},fxHeld:new Map(),selectedColumn:1,triggerDefault:'oneshot',blackout:false,master:.85,
    pending:new Map(),held:new Map(),queue:new Map(),isSaving:false,dirty:false,fetching:false,lastStructure:'',lastSnapshotSignature:'',locks:true};
const palette=['#00c89b','#1275f5','#1a54ed','#8526e6','#d326c4','#d6288b','#e76419','#53677e','#13a1ea','#253eec','#8228d9','#de316e','#f07520','#e2bc17','#05c68e','#0ab3dd','#da3993','#f2721b','#ecc01c','#09bfa5','#00afd0','#1964dc','#9439dc','#db2d9b','#8a26dd','#276ce4','#04b9a4','#f16c21','#e32973','#7238e7','#02b583','#277ceb'];
let toastTimer=0,pollHandle=0,saveTimer=0,liveStream=null;
function toast(text,bad=false){const t=$('toast');t.textContent=text;t.style.borderColor=bad?'#c43e5e':'#2b8f7b';t.classList.remove('hidden');clearTimeout(toastTimer);toastTimer=setTimeout(()=>t.classList.add('hidden'),3000)}
async function req(url,method='GET',body){const opt={method,credentials:'same-origin',headers:{}};if(body!==undefined){opt.headers['Content-Type']='application/json';opt.body=JSON.stringify(body)}const r=await fetch(url,opt);let data;try{data=await r.json()}catch{throw Error('Server tidak membalas JSON')}if(!r.ok){if(r.status===401){S.authed=false;showLogin()}throw Error(data.error||`HTTP ${r.status}`)}return data}
async function command(v,opt={}){if(!S.authed)return;try{const res=await req('/api/action','POST',v);if(!opt.quiet){$('footerStatus').textContent=res.via==='Resolume REST'?'REST SENT':'OSC SENT';}return res}catch(e){toast('Kontrol gagal: '+e.message,true);throw e}}
function queueCommand(key,v){let old=S.queue.get(key)||Promise.resolve();const next=old.catch(()=>{}).then(()=>command(v,{quiet:true}));S.queue.set(key,next);next.finally(()=>{if(S.queue.get(key)===next)S.queue.delete(key)}).catch(()=>{});return next}
function showLogin(){if(liveStream){liveStream.close();liveStream=null}S.authed=false;$('auth').classList.remove('hidden');$('app').classList.add('hidden')}
function showApp(){S.authed=true;connectLiveStream();$('auth').classList.add('hidden');$('app').classList.remove('hidden')}
async function login(){try{const pin=$('pinInput').value.trim();await req('/api/login','POST',{pin});$('pinInput').value='';showApp();await sync(true);startPolling()}catch(e){$('authMessage').textContent=e.message}}
function numeric(v,d){return typeof v==='number'&&Number.isFinite(v)?v:d}
function colorsFor(row,col){return palette[(row*7+col)%palette.length]}
function padKey(deck,row,col){return `d${deck}:l${row}:c${col}`}
function padCfg(row,col){return S.preset.pads[padKey(S.deck,row,col)]}
function currentRows(){return S.comp?.layers||[]}
function currentColumns(){return S.comp?.columns||[]}
function indexSize(){const rows=currentRows();const cols=currentColumns();return {r:rows.length,c:cols.length}}
function rowSlice(){return currentRows().slice(S.layerOffset,S.layerOffset+S.rowSize)}
function colSlice(){return currentColumns().slice(S.colOffset,S.colOffset+S.pageSize)}
function clampOffsets(){const n=indexSize();S.colOffset=Math.min(S.colOffset,Math.max(0,Math.ceil(n.c/S.pageSize)-1)*S.pageSize);S.layerOffset=Math.min(S.layerOffset,Math.max(0,Math.ceil(n.r/S.rowSize)-1)*S.rowSize);S.deck=Math.max(1,Math.min(S.deck,S.comp?.decks?.length||1));S.layer=Math.max(1,Math.min(S.layer,n.r||1))}
function selectedLayer(){return currentRows()[S.layer-1]}
function labelFor(row,col){let item=row.clips?.[col-1];const override=padCfg(row.index,col);return override?.label ?? item?.name ?? `Pad ${col}`}
function padColor(row,col){return padCfg(row.index,col)?.color||colorsFor(row.index-1,col-1)}
function sceneName(col){return currentColumns()[col-1]?.name||`Scene ${col}`}
function setStructure(){const c=S.comp;if(!c)return;clampOffsets();renderConnection();renderDecks();renderGroups();renderScenes();renderPads();renderNav();renderInspector();renderFx();renderMixer();}
function renderConnection(){const ok=S.online;$('connectDot').className='dot '+(ok?'good':'warning');$('connectionLabel').textContent=ok?'Resolume Connected':'Bridge / DEMO';$('connectionSub').textContent=ok?'REST API synchronized':'Resolume API belum tersedia';$('sidebarStatus').textContent=ok?'● LIVE SYNC':'● DEMO MODE';$('sidebarStatus').style.color=ok?'#33eeb8':'#edb75f';$('bpmLabel').textContent=S.online&&typeof S.comp?.bpm==='number'?S.comp.bpm.toFixed(1):'—';$('blackoutBtn').classList.toggle('engaged',S.blackout);$('footerStatus').textContent=ok?'RESOLUME SYNC':'DEMO • NO LIVE DATA'}
function renderDecks(){const el=$('deckList');el.replaceChildren();(S.comp?.decks||[]).forEach(d=>{const b=mk('button','deck-item'+(d.index===S.deck?' selected':''));b.title=d.name;const x=mk('b','index',d.index<=26?String.fromCharCode(64+d.index):String(d.index));const n=mk('span','name',d.name);b.append(x,n);b.onclick=async()=>{if(d.index===S.deck)return;S.deck=d.index;S.colOffset=0;setStructure();if(S.live)await command({action:'deck',deck:d.index}).catch(()=>{});await sync(true)};el.append(b)});
}
function renderGroups(){const el=$('groupList');el.replaceChildren();(S.comp?.groups||[]).forEach(g=>{const b=mk('button','group-item'+(g.index===S.group?' selected':''));b.title=g.name;b.append(mk('b','index',String(g.index)),mk('span','name',g.name));b.onclick=()=>{S.group=g.index;renderGroups();if(!S.live)toast('Group '+g.name+' dipilih untuk editing')};el.append(b)})}
function renderScenes(){const el=$('scenes');const cols=colSlice();el.style.setProperty('--ncols',cols.length||1);el.replaceChildren();for(const col of cols){const b=mk('button','scene-btn'+(S.selectedColumn===col.index?' selected':''));b.append(document.createTextNode(`Scene ${col.index}`),mk('small','',col.name));b.title='Trigger seluruh layer untuk kolom '+col.index;b.onclick=async()=>{S.selectedColumn=col.index;renderScenes();if(S.live)await command({action:'column',column:col.index}).catch(()=>{})};el.append(b)}}
function renderPads(){const el=$('padRows');el.replaceChildren();const cols=colSlice();const rows=rowSlice();const fragment=document.createDocumentFragment();
for(const row of rows){const rr=mk('div','pad-row');const name=mk('button','layer-chip'+(row.index===S.layer?' selected':''));name.append(mk('b','',`L${row.index}`),mk('small','',row.name));name.title='Select '+row.name;name.onclick=()=>{S.layer=row.index;renderMixer();renderPads()};rr.append(name);
const pads=mk('div','row-pads');pads.style.setProperty('--ncols',cols.length||1);
for(const col of cols){const cfg=padCfg(row.index,col.index)||{};const clip=row.clips?.[col.index-1];const hasClip=!!clip?.filled;const isCustom=!!cfg.osc;const key=padKey(S.deck,row.index,col.index);const b=mk('button','pad'+(!hasClip&&!isCustom?' empty':'')+(S.online&&clip?.active?' active':'')+(S.selectedPad===key&&!S.live?' studio-selected':''));
 b.dataset.key=key;b.dataset.layer=row.index;b.dataset.column=col.index;b.style.setProperty('--glow',padColor(row,col.index));b.style.backgroundColor=hasClip||isCustom||!S.live?padColor(row,col.index):'#172b39';b.title=`L${row.index} · C${col.index}: ${labelFor(row,col.index)}${S.live?'':' (edit)'}`;
 b.append(mk('span','pad-text',labelFor(row,col.index)||('PAD '+col.index)));
 if(S.online&&hasClip&&clip?.active)b.setAttribute('aria-pressed','true');
 if(S.live){b.onpointerdown=ev=>onPadDown(ev,b,row.index,col.index,hasClip,isCustom);b.onpointerup=ev=>onPadUp(ev,b);b.onpointercancel=ev=>onPadUp(ev,b);b.onlostpointercapture=ev=>onPadUp(ev,b);b.oncontextmenu=ev=>ev.preventDefault();}
 else b.onclick=()=>{S.selectedPad=key;S.editingFx=null;S.layer=row.index;renderPads();renderInspector()};
 pads.append(b)}rr.append(pads);fragment.append(rr)}el.append(fragment);
}
function onPadDown(ev,b,row,col,hasClip,isCustom){if(ev.button!==0&&ev.pointerType==='mouse')return;const key=b.dataset.key;if(!hasClip&&!isCustom)return;ev.preventDefault();S.layer=row;S.selectedColumn=col;
 const cfg=padCfg(row,col)||{};const mode=cfg.trigger||S.triggerDefault;const custom=cfg.osc;
 const v=custom?{action:'raw',address:custom,trigger:true}:{action:'clip',layer:row,column:col};
 if(mode==='piano'||mode==='hold'){
     const id=ev.pointerId;if(S.held.has(id))return;S.held.set(id,{key,v,b});b.classList.add('pressed');try{b.setPointerCapture(ev.pointerId)}catch{}
     queueCommand(key,{...v,phase:'press'}).catch(()=>{});
 }else if(mode==='toggle'){
   const active=!b.classList.contains('pad-toggle-active');b.classList.toggle('pad-toggle-active',active);queueCommand(key,{...v,phase:active?'press':'release'}).catch(()=>{});
 }else{b.classList.add('pressed');setTimeout(()=>b.classList.remove('pressed'),130);queueCommand(key,{...v,phase:'pulse'}).catch(()=>{})}
}
function onPadUp(ev,b){const hold=S.held.get(ev.pointerId);if(!hold)return;S.held.delete(ev.pointerId);hold.b.classList.remove('pressed');queueCommand(hold.key,{...hold.v,phase:'release'}).catch(()=>{});if(!S.held.size&&S.needsRender){S.needsRender=false;setStructure()}}
function releaseAllPads(){for(const [id,h] of S.held){S.held.delete(id);h.b.classList.remove('pressed');queueCommand(h.key,{...h.v,phase:'release'}).catch(()=>{})}}
function renderNav(){const {r,c}=indexSize(),cp=Math.floor(S.colOffset/S.pageSize),rp=Math.floor(S.layerOffset/S.rowSize);$('pageLabel').textContent=`PAGE ${String(cp+1).padStart(2,'0')} / ${String(Math.max(1,Math.ceil(c/S.pageSize))).padStart(2,'0')}`;
 $('layerPageLabel').textContent=`LAYERS ${r?S.layerOffset+1:0}–${Math.min(r,S.layerOffset+S.rowSize)}`;$('totalLabel').textContent=`COL ${c?S.colOffset+1:0}–${Math.min(c,S.colOffset+S.pageSize)} / ${c}`;
 $('colPrev').disabled=!S.colOffset;$('colNext').disabled=S.colOffset+S.pageSize>=c;$('layerPrev').disabled=!S.layerOffset;$('layerNext').disabled=S.layerOffset+S.rowSize>=r;
}
function fxConfig(n){return S.preset.fx?.[String(n)]||{label:'FX '+n,address:`/composition/dashboard/link${n}`,mode:'toggle',on:1,off:0,color:palette[(n*5+1)%palette.length]}}
function renderFx(){const parent=$('fxButtons');parent.replaceChildren();for(let n=1;n<=4;n++){
 const cfg=fxConfig(n);const active=!!S.fxStates[n];const b=mk('button','fx-btn'+(active?' engaged':'')+(S.editingFx===n&&!S.live?' editing':''),cfg.label||`FX ${n}`);
 b.style.background=cfg.color||palette[(n*5+1)%palette.length];b.title=cfg.address;b.dataset.fx=String(n);
 b.setAttribute('aria-pressed',String(active));
 if(S.live){b.onpointerdown=e=>onFxDown(e,n,b);b.onpointerup=e=>onFxUp(e,n,b);b.onpointercancel=e=>onFxUp(e,n,b);b.onlostpointercapture=e=>onFxUp(e,n,b)}
 else b.onclick=()=>selectFx(n);
 parent.append(b)
 }}
function selectFx(n){if(S.live)return;S.editingFx=n;S.selectedPad=null;renderPads();renderInspector();renderFx()}
function onFxDown(ev,n,b){if(ev.button!==0&&ev.pointerType==='mouse')return;ev.preventDefault();const cfg=fxConfig(n),key='fx-'+n;
 if(cfg.mode==='momentary'){if(S.fxHeld.has(ev.pointerId))return;S.fxHeld.set(ev.pointerId,{n,b});try{b.setPointerCapture(ev.pointerId)}catch{}
   S.fxStates[n]=true;renderFxState();queueCommand(key,{action:'raw',address:cfg.address,value:Number(cfg.on)}).catch(()=>{S.fxStates[n]=false;renderFxState()});}
 else if(cfg.mode==='toggle'){const next=!S.fxStates[n];S.fxStates[n]=next;renderFxState();queueCommand(key,{action:'raw',address:cfg.address,value:Number(next?cfg.on:cfg.off)}).catch(()=>{S.fxStates[n]=!next;renderFxState()})}
 else{S.fxStates[n]=true;renderFxState();queueCommand(key,{action:'raw',address:cfg.address,value:Number(cfg.on)}).then(()=>new Promise(resolve=>setTimeout(resolve,85))).then(()=>queueCommand(key,{action:'raw',address:cfg.address,value:Number(cfg.off)})).finally(()=>{S.fxStates[n]=false;renderFxState()}).catch(()=>{})}
}
function onFxUp(ev,n,b){const held=S.fxHeld.get(ev.pointerId);if(!held||held.n!==n)return;S.fxHeld.delete(ev.pointerId);const cfg=fxConfig(n);S.fxStates[n]=false;renderFxState();queueCommand('fx-'+n,{action:'raw',address:cfg.address,value:Number(cfg.off)}).catch(()=>{})}
function releaseFx(){for(const [id,h] of S.fxHeld){S.fxHeld.delete(id);const cfg=fxConfig(h.n);S.fxStates[h.n]=false;queueCommand('fx-'+h.n,{action:'raw',address:cfg.address,value:Number(cfg.off)}).catch(()=>{})}renderFxState()}
function renderFxState(){document.querySelectorAll('#fxButtons .fx-btn').forEach(b=>{const on=!!S.fxStates[+b.dataset.fx];b.classList.toggle('engaged',on);b.setAttribute('aria-pressed',String(on))})}
function renderFxInspector(){const el=$('fxInspector');el.classList.toggle('hidden',S.live||!S.editingFx);if(S.live||!S.editingFx)return;
 const n=S.editingFx,cfg=fxConfig(n);$('fxSelect').value=String(n);$('fxLabel').value=cfg.label;$('fxAddress').value=cfg.address;$('fxMode').value=cfg.mode||'toggle';$('fxOn').value=cfg.on??1;$('fxOff').value=cfg.off??0;$('fxColor').value=cfg.color||'#1775f5';$('fxColorHex').value=$('fxColor').value.toUpperCase();
}
function patchFx(){if(S.live||!S.editingFx)return;const n=S.editingFx,hex=$('fxColorHex').value.trim();if(!/^#[0-9a-f]{6}$/i.test(hex))return;
 const address=$('fxAddress').value.trim();if(!/^\/[a-zA-Z0-9_./-]{1,190}$/.test(address))return;
 const data={label:$('fxLabel').value,address,mode:$('fxMode').value,on:Number($('fxOn').value),off:Number($('fxOff').value),color:hex};
 if(!Number.isFinite(data.on)||!Number.isFinite(data.off))return;S.preset.fx[String(n)]=data;S.dirty=true;renderFx();clearTimeout(saveTimer);saveTimer=setTimeout(savePreset,650)
}
function renderMixer(){const l=selectedLayer();$('activeLayerName').textContent=l?`(${l.name} · L${S.layer})`:'—';const op=numeric(l?.opacity,1);
 if(document.activeElement!==$('opacityRange'))$('opacityRange').value=Math.round(op*100);$('opacityValue').textContent=`${$('opacityRange').value}%`;
}
function renderInspector(){const shown=!S.live;const el=$('studioInspector');el.classList.toggle('hidden',!shown);renderFxInspector();
 if(!shown)return;const form=$('inspectorForm');form.classList.toggle('hidden',!S.selectedPad||!!S.editingFx);renderFxInspector();if(!S.selectedPad||S.editingFx)return;
 const m=/d(\d+):l(\d+):c(\d+)/.exec(S.selectedPad);if(!m)return;
 const d=+m[1],r=+m[2],c=+m[3],row=currentRows()[r-1];if(!row)return;
 const cfg=S.preset.pads[S.selectedPad]||{};$('editLabel').value=cfg.label??row.clips?.[c-1]?.name??`Pad ${c}`;
 $('editColor').value=cfg.color||padColor(row,c);$('editColorHex').value=$('editColor').value.toUpperCase();$('editTrigger').value=cfg.trigger||'oneshot';$('editOsc').value=cfg.osc||'';
}
function setMode(live){if(S.live===live)return;releaseAllPads();releaseFx();S.live=live;S.selectedPad=null;S.editingFx=null;
 $('modeLive').classList.toggle('selected',live);$('modeStudio').classList.toggle('selected',!live);$('studioBar').classList.toggle('hidden',live);$('lockBtn').textContent=live?'🔒 LIVE LOCKED':'✎ STUDIO UNLOCKED';$('lockBtn').style.color=live?'#36efb8':'#ffa45f';setStructure();toast(live?'LIVE mode aktif — editing dikunci':'STUDIO mode — clip trigger dimatikan')}
function patchPad(){if(S.live||!S.selectedPad)return;const color=$('editColorHex').value.trim();if(!/^#[0-9a-f]{6}$/i.test(color))return;S.dirty=true;const value={label:$('editLabel').value,color,trigger:$('editTrigger').value,osc:$('editOsc').value.trim()};S.preset.pads[S.selectedPad]=value;renderPads();clearTimeout(saveTimer);saveTimer=setTimeout(savePreset,600)}
async function savePreset(){try{S.isSaving=true;await req('/api/preset','POST',S.preset);S.dirty=false;$('footerStatus').textContent='PRESET SAVED'}catch(e){toast('Gagal simpan: '+e.message,true)}finally{S.isSaving=false}}
function exportPreset(){if(window.PulseAndroid?.saveJSON){window.PulseAndroid.saveJSON(JSON.stringify(S.preset,null,2));return}const blob=new Blob([JSON.stringify(S.preset,null,2)],{type:'application/json'});const url=URL.createObjectURL(blob);const a=document.createElement('a');a.href=url;a.download='pulse_arena_v3_preset.json';document.body.append(a);a.click();a.remove();setTimeout(()=>URL.revokeObjectURL(url),1000)}
async function importPreset(file){try{const text=await file.text();const obj=JSON.parse(text);const result=await req('/api/preset','POST',obj);S.preset=result.preset;renderPads();renderFx();renderInspector();toast('Preset berhasil diimpor')}catch(e){toast('Preset invalid: '+e.message,true)}}
async function sync(force=false){if(S.fetching||!S.authed)return;S.fetching=true;try{const result=await req('/api/state');S.cfg=result.config;S.preset=(S.isSaving||S.dirty)?S.preset:result.preset;S.comp=result.composition;S.online=result.api_connected;S.source=result.composition.source;S.blackout=!!result.blackout;S.fxFeedback=result.fx_feedback||{};
  for(let n=1;n<=4;n++){const cfg=fxConfig(n);if(Object.prototype.hasOwnProperty.call(S.fxFeedback,cfg.address)){
    const v=S.fxFeedback[cfg.address];if(typeof v==='number')S.fxStates[n]=Math.abs(v-(cfg.on??1))<Math.abs(v-(cfg.off??0));
  }}renderFxState();
  if(result.composition.source==='resolume'&&result.composition.selected_deck){S.deck=result.composition.selected_deck}else if(force&&!S.lastStructure){S.deck=result.composition.selected_deck||S.deck}S.lastStructure='ready';
  const compForHash={...result.composition};delete compForHash.updated_at;
  const hash=JSON.stringify([compForHash,S.deck,S.group,S.colOffset,S.layerOffset,S.pageSize,S.rowSize]);
  if(S.held.size){S.needsRender=true;renderConnection();return}
  const editing=!S.live&&($('studioInspector').contains(document.activeElement)||$('fxInspector').contains(document.activeElement));
  if(!force&&hash===S.lastSnapshotSignature){renderConnection();return}
  if(editing){renderConnection();return}
  S.lastSnapshotSignature=hash;setStructure();}catch(e){$('connectDot').className='dot warning';$('connectionLabel').textContent='Bridge disconnected';$('footerStatus').textContent='CONNECTION LOST';}finally{S.fetching=false}}
function connectLiveStream(){
 if(liveStream||typeof EventSource==='undefined'||!/^https?:$/.test(location.protocol))return;
 liveStream=new EventSource('/api/events');
 liveStream.onmessage=e=>{let event;try{event=JSON.parse(e.data)}catch{return}
   if(typeof event.bpm==='number'&&Number.isFinite(event.bpm)){
     if(S.comp&&S.online)S.comp.bpm=event.bpm;
     if(S.online)$('bpmLabel').textContent=event.bpm.toFixed(1);
   }
   if(event.clip&&S.comp&&S.online){const {layer,column,active}=event.clip;
     const row=S.comp.layers?.[layer-1];if(row&&row.clips?.[column-1]){
       if(active){for(const clip of row.clips)clip.active=false;
         document.querySelectorAll(`#padRows .pad[data-layer="${layer}"]`).forEach(el=>{el.classList.remove('active');el.setAttribute('aria-pressed','false')});}
       row.clips[column-1].active=!!active;
       const pad=document.querySelector(`#padRows .pad[data-layer="${layer}"][data-column="${column}"]`);
       if(pad){pad.classList.toggle('active',!!active);pad.setAttribute('aria-pressed',String(!!active))}
     }
   }
   if(event.fx){const {address,value}=event.fx;for(let n=1;n<=4;n++){const cfg=fxConfig(n);
     if(cfg.address===address&&typeof value==='number')S.fxStates[n]=Math.abs(value-(cfg.on??1))<Math.abs(value-(cfg.off??0));}renderFxState();}
   if(typeof event.master_opacity==='number'&&S.comp)S.comp.master_opacity=event.master_opacity;
 };
}
function startPolling(){if(pollHandle)clearInterval(pollHandle);pollHandle=setInterval(()=>{if(!document.hidden)sync()},650)}
function openSettings(){req('/api/ports').then(({ports})=>{const s=$('cfgMidi');s.replaceChildren(new Option('None',''));for(const p of ports)s.add(new Option(p,p));s.value=S.cfg?.midi_output||''}).catch(()=>{});
 const c=S.cfg||{};$('cfgHost').value=c.resolume_host||'127.0.0.1';$('cfgRestPort').value=c.resolume_api_port||8080;$('cfgOscPort').value=c.osc_port||7000;$('cfgFeedbackPort').value=c.osc_feedback_port||7700;$('cfgTransport').value=c.transport||'osc';$('cfgPageSize').value=String(S.pageSize);$('cfgLayerSize').value=String(S.rowSize);$('cfgDemoRows').value=c.manual_layers||8;$('cfgDemoCols').value=c.manual_columns||48;$('scrim').classList.remove('hidden');$('settingsModal').classList.remove('hidden')}
function closeSettings(){$('scrim').classList.add('hidden');$('settingsModal').classList.add('hidden')}
async function saveSettings(){try{const config={resolume_host:$('cfgHost').value.trim(),resolume_api_port:+$('cfgRestPort').value,osc_port:+$('cfgOscPort').value,osc_feedback_port:+$('cfgFeedbackPort').value,transport:$('cfgTransport').value,
  midi_output:$('cfgMidi').value,manual_layers:+$('cfgDemoRows').value,manual_columns:+$('cfgDemoCols').value};
 await req('/api/config','POST',config);S.pageSize=+$('cfgPageSize').value;S.rowSize=+$('cfgLayerSize').value;storage.set('columns',S.pageSize);storage.set('layers',S.rowSize);S.colOffset=0;S.layerOffset=0;closeSettings();await sync(true);toast('Settings tersimpan')}catch(e){toast(e.message,true)}}
function binding(){
 $('loginBtn').onclick=login;$('pinInput').addEventListener('keydown',e=>{if(e.key==='Enter')login()});
 $('modeLive').onclick=()=>setMode(true);$('modeStudio').onclick=()=>setMode(false);
 $('lockBtn').onclick=()=>setMode(!S.live);$('settingsBtn').onclick=openSettings;
 $('scrim').onclick=closeSettings;document.querySelectorAll('[data-close]').forEach(b=>b.onclick=closeSettings);
 $('saveSettings').onclick=saveSettings;$('logoutBtn').onclick=async()=>{try{await req('/api/logout','POST',{})}catch{}closeSettings();showLogin()};
 $('colPrev').onclick=()=>{S.colOffset=Math.max(0,S.colOffset-S.pageSize);setStructure()};$('colNext').onclick=()=>{S.colOffset+=S.pageSize;clampOffsets();setStructure()};
 $('layerPrev').onclick=()=>{S.layerOffset=Math.max(0,S.layerOffset-S.rowSize);setStructure()};$('layerNext').onclick=()=>{S.layerOffset+=S.rowSize;clampOffsets();setStructure()};
 $('decksPrev').onclick=()=>{const d=S.comp?.decks||[];if(S.deck>1){S.deck--;S.colOffset=0;setStructure();if(S.live)command({action:'deck',deck:S.deck}).catch(()=>{})}};
 $('decksNext').onclick=()=>{const d=S.comp?.decks||[];if(S.deck<d.length){S.deck++;S.colOffset=0;setStructure();if(S.live)command({action:'deck',deck:S.deck}).catch(()=>{})}};
 $('dockBtn').onclick=()=>{S.dockVisible=!S.dockVisible;$('dock').classList.toggle('hidden',!S.dockVisible)};
 $('fitGrid').onclick=()=>{S.pageSize=S.pageSize===10?8:10;storage.set('columns',S.pageSize);S.colOffset=0;setStructure();toast(`Grid: ${S.pageSize} kolom per bank`)};
 $('opacityRange').oninput=e=>{$('opacityValue').textContent=e.target.value+'%'};
 $('opacityRange').onchange=e=>command({action:'opacity',layer:S.layer,value:+e.target.value/100}).catch(()=>{});
 $('speedRange').oninput=e=>{$('speedValue').textContent=(+e.target.value/100).toFixed(2)+'x'};
 $('speedRange').onchange=e=>command({action:'speed',layer:S.layer,value:+e.target.value/100}).catch(()=>{});
 $('volumeRange').oninput=e=>{$('volumeValue').textContent=e.target.value+'%'};
 $('volumeRange').onchange=e=>command({action:'volume',layer:S.layer,value:+e.target.value/100}).catch(()=>{});
 $('masterRange').oninput=e=>{$('masterLabel').textContent=e.target.value+'%'};
 $('masterRange').onchange=e=>command({action:'master',value:+e.target.value/100}).catch(()=>{});
 $('crossfaderRange').onchange=e=>command({action:'crossfader',value:+e.target.value/100}).catch(()=>{});
 $('transitionDuration').oninput=e=>{$('transitionValue').textContent=(+e.target.value).toFixed(1)+'s'};
 $('transitionDuration').onchange=e=>command({action:'transition',layer:S.layer,value:+e.target.value}).catch(()=>{});
 $('transitionMode').onchange=e=>{document.querySelectorAll('.trans-pad').forEach(b=>b.classList.toggle('selected',b.dataset.transition===e.target.value));command({action:'transitionmode',layer:S.layer,name:e.target.value}).catch(()=>{})};
 document.querySelectorAll('.trans-pad').forEach(b=>b.onclick=()=>{$('transitionMode').value=b.dataset.transition;$('transitionMode').dispatchEvent(new Event('change'))});
 $('tapBtn').onclick=()=>command({action:'tap'}).catch(()=>{});
 // Blackout requires deliberate pointer hold, restore is a normal click.
 let blackoutTimer;const black=$('blackoutBtn');black.onpointerdown=e=>{if(e.button!==0&&e.pointerType==='mouse')return;e.preventDefault();if(S.blackout){command({action:'blackout',enabled:false}).then(()=>{S.blackout=false;black.classList.remove('engaged');toast('BLACKOUT OFF — output restored')}).catch(()=>{});return}blackoutTimer=setTimeout(()=>{command({action:'blackout',enabled:true}).then(()=>{S.blackout=true;black.classList.add('engaged');toast('BLACKOUT ON — tap untuk RESTORE')}).catch(()=>{})},750)};
 for(const ev of ['pointerup','pointercancel','pointerleave'])black.addEventListener(ev,()=>clearTimeout(blackoutTimer));
 $('clearBtn').onclick=$('layerClear').onclick=$('stopSelectedBtn').onclick=()=>command({action:'clear',layer:S.layer}).catch(()=>{});
 $('groupClearBtn').onclick=()=>{if(!S.live)return toast('LIVE mode untuk CLEAR GROUP');if(!S.online)return toast('CLEAR GROUP membutuhkan REST API Resolume aktif',true);if(confirm('Clear semua clip aktif pada group '+S.group+'?'))command({action:'groupclear',group:S.group}).catch(()=>{})};
 $('selectPrevClipBtn').onclick=()=>{S.selectedColumn=Math.max(1,S.selectedColumn-1);S.colOffset=Math.floor((S.selectedColumn-1)/S.pageSize)*S.pageSize;setStructure()};
 $('selectNextClipBtn').onclick=()=>{S.selectedColumn=Math.min(indexSize().c,S.selectedColumn+1);S.colOffset=Math.floor((S.selectedColumn-1)/S.pageSize)*S.pageSize;setStructure()};
 $('quickOneshot').onclick=()=>{S.triggerDefault='oneshot';$('quickOneshot').classList.add('selected');$('quickPiano').classList.remove('selected')};
 $('quickPiano').onclick=()=>{S.triggerDefault='piano';$('quickPiano').classList.add('selected');$('quickOneshot').classList.remove('selected')};
 $('bypassBtn').onclick=()=>command({action:'raw',address:`/composition/layers/${S.layer}/bypassed`,value:1,trigger:false}).catch(()=>{});
 $('soloBtn').onclick=()=>command({action:'raw',address:`/composition/layers/${S.layer}/solo`,value:1}).catch(()=>{});
 $('outputBtn').onclick=()=>toast('Output display diatur melalui Resolume Advanced Output');
 $('syncBtn').onclick=()=>sync(true);$('gridView').onclick=()=>toast('Dynamic Grid aktif');$('favoriteBtn').onclick=()=>toast('Favorites direncanakan pada pembaruan berikutnya');$('triggerModeBtn').onclick=()=>toast('Trigger mode: '+S.triggerDefault.toUpperCase());
 ['editLabel','editTrigger','editOsc'].forEach(id=>$(id).addEventListener('input',patchPad));
 $('editColor').addEventListener('input',()=>{$('editColorHex').value=$('editColor').value.toUpperCase();patchPad()});
 $('editColorHex').addEventListener('input',()=>{const v=$('editColorHex').value.trim();if(/^#[0-9a-f]{6}$/i.test(v)){$('editColor').value=v;patchPad()}});
 $('copyHex').onclick=async()=>{const hex=$('editColorHex').value.toUpperCase();if(!/^#[0-9A-F]{6}$/.test(hex))return toast('Kode HEX tidak valid',true);try{await navigator.clipboard.writeText(hex);toast('HEX disalin: '+hex)}catch{const i=$('editColorHex');i.focus();i.select();try{document.execCommand('copy');toast('HEX disalin: '+hex)}catch{toast('Pilih lalu salin kode HEX secara manual',true)}}};
 $('fxSelect').onchange=e=>selectFx(+e.target.value);
 ['fxLabel','fxAddress','fxMode','fxOn','fxOff'].forEach(id=>$(id).addEventListener('input',patchFx));
 $('fxColor').addEventListener('input',()=>{$('fxColorHex').value=$('fxColor').value.toUpperCase();patchFx()});
 $('fxColorHex').addEventListener('input',()=>{const v=$('fxColorHex').value.trim();if(/^#[0-9a-f]{6}$/i.test(v)){$('fxColor').value=v;patchFx()}});
 $('fxReset').onclick=()=>{delete S.preset.fx[String(S.editingFx)];S.dirty=true;renderFx();renderFxInspector();clearTimeout(saveTimer);saveTimer=setTimeout(savePreset,250)};
 $('resetPad').onclick=()=>{if(!S.selectedPad)return;delete S.preset.pads[S.selectedPad];renderPads();renderInspector();clearTimeout(saveTimer);saveTimer=setTimeout(savePreset,250)};
 $('savePreset').onclick=savePreset;$('presetExport').onclick=exportPreset;$('presetImport').onclick=()=>$('presetFile').click();$('presetFile').onchange=e=>{if(e.target.files?.[0])importPreset(e.target.files[0]);e.target.value=''};
 $('editFx').onclick=$('studioFxBtn').onclick=()=>{setMode(false);selectFx(1);toast('Quick FX editor aktif')};
 document.addEventListener('visibilitychange',()=>{if(document.hidden){releaseAllPads();releaseFx()}else if(S.authed)sync()});window.addEventListener('blur',()=>{releaseAllPads();releaseFx()});
}
async function main(){binding();try{const session=await req('/api/session');if(session.authenticated){showApp();await sync(true);startPolling()}else showLogin()}catch{showLogin();$('authMessage').textContent='Bridge tidak tersedia. Jalankan server.py / run_windows.bat.'}}
main();
})();
