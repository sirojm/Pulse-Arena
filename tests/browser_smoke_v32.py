"""Offline frontend smoke test using mocked REST responses. Requires playwright & Chromium.
Does NOT test real Resolume nor OSC transport.
"""
import json
from pathlib import Path
from playwright.sync_api import sync_playwright
ROOT=Path(__file__).resolve().parents[1]
raw={'name':'Smoke Show','tempocontroller':{'tempo':{'value':138.5}},'video':{'opacity':{'value':0.8}},
 'decks':[{'index':1,'name':'Arena','selected':True}],
 'layers':[{'index':row+1,'name':f'Layer {row+1}','opacity':1,'clips':[{'index':i+1,'name':f'Clip {i+1}','filled':True,'active':i==0} for i in range(10)]} for row in range(5)],
 'columns':[{'index':i+1,'name':f'Scene {i+1}'} for i in range(10)],'groups':[], 'selected_deck':1,
 'bpm':138.5, 'source':'resolume'}
mock=r'''<script>
let preset={version:3,name:'Test Show',pads:{},fx:{}},blackout=false;
window.fetch=async(url,opts={})=>{
 const path=String(url),body=opts.body?JSON.parse(opts.body):{};
 let out={ok:true,via:'OSC'};
 if(path==='/api/session')out={authenticated:true};
 if(path==='/api/state')out={version:'3.2.0',api_connected:true,composition:__COMPOSITION__,preset,config:{osc_port:7000,osc_feedback_port:7700,poll_interval:1.2},blackout,fx_feedback:{}};
 if(path==='/api/preset'){preset=body;out={ok:true,preset}};
 if(path==='/api/action'&&body.action==='blackout'){blackout=body.enabled;out={ok:true,via:'OSC'}};
 if(path==='/api/ports')out={ports:[]};
 return new Response(JSON.stringify(out),{status:200,headers:{'content-type':'application/json'}});
}
</script>'''.replace('__COMPOSITION__',json.dumps(raw))
html=(ROOT/'static/index.html').read_text().replace('<link rel="stylesheet" href="/style.css">','<style>'+ (ROOT/'static/style.css').read_text()+'</style>')
html=html.replace('<script src="/app.js"></script>',mock+'<script>'+ (ROOT/'static/app.js').read_text()+'</script>')
with sync_playwright() as p:
 browser=p.chromium.launch(headless=True,executable_path='/usr/bin/chromium',args=['--no-sandbox','--disable-gpu'])
 page=browser.new_page(viewport={'width':1330,'height':790},device_scale_factor=1)
 errors=[];page.on('pageerror',lambda exc:errors.append(str(exc)))
 page.set_content(html,wait_until='load')
 page.locator('#app:not(.hidden)').wait_for(timeout=7000)
 page.locator('#bpmLabel').filter(has_text='138.5').wait_for(timeout=7000)
 assert page.locator('.pad.active').count()==5
 page.locator('#blackoutBtn').dispatch_event('pointerdown',{'pointerId':101,'button':0,'pointerType':'mouse'})
 page.wait_for_timeout(950)
 assert page.locator('#blackoutBtn').evaluate('(el)=>el.classList.contains("engaged")')
 page.locator('#blackoutBtn').dispatch_event('pointerup',{'pointerId':101,'button':0,'pointerType':'mouse'})
 page.locator('#blackoutBtn').dispatch_event('pointerdown',{'pointerId':102,'button':0,'pointerType':'mouse'})
 page.wait_for_timeout(250)
 assert not page.locator('#blackoutBtn').evaluate('(el)=>el.classList.contains("engaged")')
 page.locator('#blackoutBtn').dispatch_event('pointerup',{'pointerId':102,'button':0,'pointerType':'mouse'})
 page.locator('#modeStudio').click()
 page.locator('.pad').first.click()
 page.locator('#editColorHex').fill('#ABC123')
 assert page.locator('#editColor').input_value().lower()=='#abc123'
 page.locator('#editFx').click()
 page.locator('#fxInspector:not(.hidden)').wait_for(timeout=3000)
 page.locator('#fxLabel').fill('Glitch ON/OFF')
 page.locator('#fxMode').select_option('toggle')
 page.wait_for_timeout(800)
 assert page.evaluate('preset.fx["1"].label')=='Glitch ON/OFF'
 page.locator('#modeLive').click()
 page.locator('#fxButtons .fx-btn').first.dispatch_event('pointerdown',{'pointerId':10,'button':0,'pointerType':'mouse'})
 page.wait_for_timeout(120)
 assert page.locator('#fxButtons .fx-btn').first.get_attribute('aria-pressed')=='true'
 page.locator('#fxButtons .fx-btn').first.dispatch_event('pointerdown',{'pointerId':11,'button':0,'pointerType':'mouse'})
 page.wait_for_timeout(120)
 assert page.locator('#fxButtons .fx-btn').first.get_attribute('aria-pressed')=='false'
 page.screenshot(path=str(ROOT/'preview_v3_0_1_tablet.png'))
 assert not errors,errors
 phone=browser.new_page(viewport={'width':915,'height':412},device_scale_factor=1)
 phone_err=[];phone.on('pageerror',lambda exc:phone_err.append(str(exc)))
 phone.set_content(html,wait_until='load')
 phone.locator('#app:not(.hidden)').wait_for(timeout=7000)
 phone.screenshot(path=str(ROOT/'preview_v3_0_1_phone.png'))
 assert not phone_err,phone_err
 print('PASS: Browser UI, BPM, pad glow, blackout restore, HEX, FX editor and ON/OFF')
 browser.close()
