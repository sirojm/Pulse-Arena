"""PULSE ARENA 3.0 — private-LAN Resolume performance controller bridge.
Python 3.10+ standard library for OSC + REST composition sync. MIDI optional mido/rtmidi.
"""
import json, os, re, time, hmac, secrets, socket, struct, threading, logging, mimetypes, math
from collections import deque, defaultdict
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from http.cookies import SimpleCookie
from pathlib import Path
from urllib.parse import urlsplit
from urllib.request import Request, urlopen
from urllib.error import URLError, HTTPError

ROOT = Path(__file__).resolve().parent
STATIC = ROOT/'static'; DATA = ROOT/'data'; DATA.mkdir(exist_ok=True)
CONFIG_PATH = DATA/'settings.json'; PRESET_PATH = DATA/'preset.json'
DEFAULT = {'resolume_host':'127.0.0.1','resolume_api_port':8080,'osc_port':7000,
           'web_port':8787,'transport':'osc','midi_output':'','manual_layers':8,
           'manual_columns':48,'manual_decks':4,'manual_groups':4,'poll_interval':1.2,'osc_feedback_port':7700}
LOG=logging.getLogger('pulse')

def clampint(x,lo,hi):
    if isinstance(x,bool) or not isinstance(x,(int,float,str)) or not str(x).isdigit(): raise ValueError('Angka tidak valid')
    a=int(x)
    if not lo<=a<=hi: raise ValueError(f'Angka harus {lo}–{hi}')
    return a

def rangefloat(x,lo,hi):
    if type(x) not in (float,int) or not lo <= x <= hi: raise ValueError(f'Angka harus {lo}–{hi}')
    return float(x)

def osc_string(value):
    x=str(value).encode('utf-8')+b'\x00'
    return x + b'\x00'*((-len(x))%4)

def osc_packet(address, values):
    if not isinstance(address,str) or not re.fullmatch(r'/[\w./-]{1,190}',address, flags=re.ASCII): raise ValueError('OSC address tidak valid')
    typ=','; data=b''
    for x in values:
        if type(x) is int and -(2**31)<=x<2**31: typ+='i';data+=struct.pack('>i',x)
        elif type(x) is float and -1e9<x<1e9: typ+='f';data+=struct.pack('>f',x)
        elif isinstance(x,str) and len(x)<=100: typ+='s';data+=osc_string(x)
        else: raise ValueError('Nilai OSC tidak valid')
    return osc_string(address)+osc_string(typ)+data

def parse_osc_messages(packet):
    """Parse lightweight OSC messages and bundles from Resolume output.
    Unknown tags are discarded rather than interpreted as values.
    """
    def aligned(data, pos):
        end=data.find(b'\0',pos)
        if end<0: raise ValueError('Missing OSC string terminator')
        return data[pos:end].decode('utf-8','replace'),(end+4)&~3
    if packet.startswith(b'#bundle\0'):
        pos=16
        while pos+4<=len(packet):
            n=struct.unpack_from('>i',packet,pos)[0];pos+=4
            if n<=0 or pos+n>len(packet):break
            yield from parse_osc_messages(packet[pos:pos+n]);pos+=n
        return
    try:
        addr,pos=aligned(packet,0)
        tags,pos=aligned(packet,pos)
        if not addr.startswith('/') or not tags.startswith(','):return
        args=[]
        for tag in tags[1:]:
            if tag=='i': v=struct.unpack_from('>i',packet,pos)[0];pos+=4
            elif tag=='f':v=struct.unpack_from('>f',packet,pos)[0];pos+=4
            elif tag=='s':v,pos=aligned(packet,pos)
            elif tag=='T':v=True
            elif tag=='F':v=False
            else:return
            args.append(v)
        yield addr,args
    except (ValueError,UnicodeError,struct.error,IndexError):return


def bpm_number(v):
    v=param(v,None)
    try:
        n=float(v)
        return round(n,3) if math.isfinite(n) and 20<=n<=300 else None
    except (TypeError,ValueError):return None

def param(value,default=''):
    if isinstance(value,dict):
        if 'value' in value: return param(value['value'],default)
        if 'name' in value: return param(value['name'],default)
    return value if value is not None else default

def textparam(value,default=''):
    val=param(value,default)
    return str(val) if isinstance(val,(int,float,str)) else default

def boolparam(value):
    val=param(value,False)
    if isinstance(val,str): return val.lower() in ('true','1','yes')
    return bool(val)

def listify(value):
    if isinstance(value,list): return value
    if isinstance(value,dict):
        if 'items' in value and isinstance(value['items'],list):return value['items']
        # avoid guessing arbitrary object values, only positional numeric keyed dictionaries
        if value and all(str(k).isdigit() for k in value):return [value[k] for k in sorted(value,key=lambda k:int(k))]
    return []

def normalize_comp(raw):
    """Lightweight snapshots, avoids shipping media thumbnails and huge effects trees."""
    if not isinstance(raw,dict):raise ValueError('Composition API tidak sesuai')
    layers=listify(raw.get('layers'));columns=listify(raw.get('columns'));decks=listify(raw.get('decks'))
    groups=listify(raw.get('layergroups',raw.get('groups',[])))
    # Clips can appear as a per-layer list. Count from columns when supplied.
    ncol=max(len(columns),max((len(listify(layer.get('clips'))) for layer in layers if isinstance(layer,dict)),default=0))
    selected_deck=0
    result_decks=[]
    for i,d in enumerate(decks,1):
        d=d if isinstance(d,dict) else {}
        selected=boolparam(d.get('selected',False))
        if selected:selected_deck=i
        result_decks.append({'index':i,'id':str(d.get('id',i)),'name':textparam(d.get('name'),f'Deck {i}'),'selected':selected})
    result_columns=[]
    for i in range(ncol):
        c=columns[i] if i<len(columns) and isinstance(columns[i],dict) else {}
        result_columns.append({'index':i+1,'name':textparam(c.get('name'),f'Scene {i+1}'),'id':str(c.get('id',i+1))})
    result_layers=[]
    for i,l in enumerate(layers,1):
        l=l if isinstance(l,dict) else {};clips=listify(l.get('clips'))
        result_clips=[]
        for j in range(ncol):
            clip=clips[j] if j<len(clips) and isinstance(clips[j],dict) else {}
            clip_name=textparam(clip.get('name'),'')
            # Rendering empty positions deliberately: None means there's no loaded clip.
            has_content=bool(clip.get('video') or clip.get('audio') or clip.get('source') or (clip_name and clip_name.lower() not in ('empty','empty clip')))
            if 'is_empty' in clip:has_content=not boolparam(clip['is_empty'])
            result_clips.append({'index':j+1,'id':str(clip.get('id','')),
                'name':clip_name,'filled':has_content,'active':boolparam(clip.get('connected',False)),'active_known':'connected' in clip})
        result_layers.append({'index':i,'id':str(l.get('id',i)),'name':textparam(l.get('name'),f'Layer {i}'),
            'selected':boolparam(l.get('selected',False)),'opacity':param(l.get('video',{}).get('opacity',1),1) if isinstance(l.get('video'),dict) else 1,
            'clips':result_clips})
    result_groups=[]
    for i,g in enumerate(groups,1):
        g=g if isinstance(g,dict) else {}
        result_groups.append({'index':i,'id':str(g.get('id',i)),'name':textparam(g.get('name'),f'Group {i}')})
    tempo=raw.get('tempocontroller',{})
    bpm=bpm_number(tempo.get('tempo')) if isinstance(tempo,dict) else None
    video=raw.get('video',{})
    master=param(video.get('opacity'),None) if isinstance(video,dict) else None
    try:master=float(master) if master is not None else None
    except (ValueError,TypeError):master=None
    bypassed=boolparam(raw.get('bypassed',False))
    return {'source':'resolume','name':textparam(raw.get('name'),'Resolume Composition'),'layers':result_layers,
            'columns':result_columns,'decks':result_decks,'groups':result_groups,
            'selected_deck':selected_deck,'bpm':bpm,'master_opacity':master,'bypassed':bypassed,'updated_at':time.time()}

def demo_comp(config):
    labels=[['Intro','BG Loop','Sky','Particles','Wave','Aerial','Cloud','Nebula','Space','Outro'],
            ['Build','Drop','Break','Strobe','Laser','Smoke','Burst','Hit','Riser','Wipe'],
            ['Logo','Text 1','Text 2','Text 3','Quote','Shape','Line Art','Frame','Gradient','Lower3rd'],
            ['FX A','FX B','FX C','Flash','Strobe 2','Beat','Pattern','Glitch','Distort','Colorize'],
            ['Cam 1','Cam 2','Cam 3','Cam 4','Live In','Camera FX','Zoom','Angle','Split','CCTV'],
            ['DJ','Crowd','Stage','Audience','Closeup','Wide','Cut','Slow','Replay','BTS'],
            ['Mask','Matte','Invert','Kaleido','Mirror','Blur','Pixel','RGB','Noise','Vignette'],
            ['Key','Alpha','Luma','Chroma','Solid','Border','Shadow','Frame','Grid','Custom']]
    ncol=config['manual_columns']; nlay=config['manual_layers']
    layers=[]
    for i in range(nlay):
        row=labels[i%len(labels)];layers.append({'index':i+1,'id':str(i+1),'name':(['BG','Visual','Text','FX','Cam','Audio','Extra','Mask'][i%8]),'selected':i==1,'opacity':1,
                   'clips':[{'index':j+1,'id':str((i+1)*10000+j+1),'name':row[j%len(row)] if j<min(ncol,10) else f'Clip {j+1}',
                             'filled':True,'active':False} for j in range(ncol)]})
    return {'source':'demo','name':'Demo — tidak terhubung ke Resolume','layers':layers,
        'columns':[{'index':i+1,'id':str(i+1),'name':f'Scene {i+1}'} for i in range(ncol)],
        'decks':[{'index':i+1,'id':str(i+1),'name':(['Arena','Stage','Screens','Floor'][i] if i<4 else f'Deck {i+1}'),'selected':i==0} for i in range(config['manual_decks'])],
        'groups':[{'index':i+1,'id':str(i+1),'name':(['Main','Visuals','Textures','FX','Audio','Stills'][i] if i<6 else f'Group {i+1}')} for i in range(config['manual_groups'])],
        'selected_deck':1,'bpm':128,'master_opacity':1.0,'bypassed':False,'updated_at':time.time()}

def valid_preset(p):
    if not isinstance(p,dict):raise ValueError('Preset harus JSON object')
    pads=p.get('pads',{});fx=p.get('fx',{})
    if not isinstance(pads,dict) or len(pads)>10000:raise ValueError('Jumlah pad terlalu banyak')
    if not isinstance(fx,dict) or len(fx)>8:raise ValueError('FX tidak valid')
    clean={}
    for k,v in pads.items():
        if not isinstance(k,str) or not re.fullmatch(r'd[0-9]{1,5}:l[0-9]{1,5}:c[0-9]{1,5}',k):raise ValueError('ID pad tidak valid')
        if not isinstance(v,dict):raise ValueError('Pad tidak valid')
        label=v.get('label','');color=v.get('color','#08CFA4');trigger=v.get('trigger','oneshot');osc=v.get('osc','')
        if not isinstance(label,str) or len(label)>90 or not isinstance(color,str) or not re.fullmatch(r'#[0-9a-fA-F]{6}',color):raise ValueError('Nama / warna pad tidak valid')
        if trigger not in ('oneshot','piano','toggle','hold'):raise ValueError('Trigger tidak valid')
        if not isinstance(osc,str) or (osc and not re.fullmatch(r'/[a-zA-Z0-9_./-]{1,190}',osc)):raise ValueError('OSC custom tidak valid')
        clean[k]={'label':label,'color':color,'trigger':trigger,'osc':osc}
    clean_fx={}
    for k,v in fx.items():
        if not re.fullmatch(r'[1-8]',str(k)) or not isinstance(v,dict):raise ValueError('FX tidak valid')
        name=v.get('label',f'FX {k}');address=v.get('address',f'/composition/dashboard/link{k}')
        mode=v.get('mode','toggle'); color=v.get('color','#1775f5')
        on=v.get('on',1);off=v.get('off',0)
        if not isinstance(name,str) or len(name)>24 or not isinstance(address,str) or not re.fullmatch(r'/[a-zA-Z0-9_./-]{1,190}',address):raise ValueError('Macro tidak valid')
        if mode not in ('toggle','momentary','pulse'):raise ValueError('Mode FX tidak valid')
        if not isinstance(color,str) or not re.fullmatch(r'#[0-9a-fA-F]{6}',color):raise ValueError('Warna FX tidak valid')
        if any(type(x) not in (int,float) or not math.isfinite(x) or not -100000<=x<=100000 for x in (on,off)):
            raise ValueError('Nilai FX tidak valid')
        clean_fx[str(k)]={'label':name,'address':address,'mode':mode,'on':on,'off':off,'color':color}
    return {'version':3,'name':str(p.get('name','My Show'))[:90],'pads':clean,'fx':clean_fx}

class Pulse:
    def __init__(self):
        self.lock=threading.RLock();self.config=DEFAULT.copy();self.pin=os.getenv('PULSE_PIN') or f'{secrets.randbelow(1000000):06d}'
        self.sessions={};self.failures=defaultdict(deque);self.udp=socket.socket(socket.AF_INET,socket.SOCK_DGRAM)
        self.midi=None;self.midi_name='';self.held=set();self.timers={};self.snapshot=None;self.last_sync=0;self.last_error=''
        self.active_phases=set();self.toggles={};self.feedback_clips={};self.feedback_fx={}
        self.feedback_bpm=None;self.feedback_bpm_at=0;self.blackout=False;self.blackout_master=1.0
        self.feedback_blackout=None;self.feedback_blackout_at=0;self.feedback_master=None;self.feedback_master_at=0
        self.feedback_ready=False;self.live_seq=0;self.last_live_event={};self.live_cv=threading.Condition(self.lock)
        if CONFIG_PATH.exists():
            try:self.config.update({k:v for k,v in json.loads(CONFIG_PATH.read_text('utf-8')).items() if k in DEFAULT})
            except (ValueError,OSError):pass
        self.preset={'version':3,'name':'My Show','pads':{},'fx':{}}
        if PRESET_PATH.exists():
            try:self.preset=valid_preset(json.loads(PRESET_PATH.read_text('utf-8')))
            except (ValueError,OSError):pass
        threading.Thread(target=self.poll,daemon=True).start()
        threading.Thread(target=self.listen_feedback,daemon=True).start()

    def listen_feedback(self):
        """Receive Resolume OSC Output on loopback, not accessible from the public LAN."""
        s=socket.socket(socket.AF_INET,socket.SOCK_DGRAM)
        try:s.bind(('127.0.0.1',self.config['osc_feedback_port']))
        except OSError as exc:
            LOG.warning('OSC feedback port unavailable: %s',exc);s.close();return
        s.settimeout(1)
        self.feedback_ready=True
        while True:
            try:packet,_=s.recvfrom(65535)
            except socket.timeout:continue
            except OSError:break
            for addr,args in parse_osc_messages(packet):
                if not args:continue
                value=args[0];now=time.monotonic()
                with self.lock:
                    if addr in ('/composition/tempocontroller/tempo','/composition/tempocontroller/bpm'):
                        n=bpm_number(value)
                        if n is not None:
                            self.feedback_bpm=n;self.feedback_bpm_at=now;self.push_live({'bpm':n})
                    elif addr=='/composition/bypassed':
                        self.feedback_blackout=boolparam(value);self.feedback_blackout_at=now;self.push_live({'bypassed':self.feedback_blackout})
                    elif addr=='/composition/video/opacity':
                        try:
                            self.feedback_master=float(value);self.feedback_master_at=now;self.push_live({'master_opacity':self.feedback_master})
                        except (TypeError,ValueError):pass
                    elif re.fullmatch(r'/composition/dashboard/link[1-8]',addr):
                        self.feedback_fx[addr]=(value,now);self.push_live({'fx':{'address':addr,'value':value}})
                    else:
                        m=re.fullmatch(r'/composition/layers/(\d+)/clips/(\d+)/connected',addr)
                        if m:
                            layer,column=int(m[1]),int(m[2]);active=boolparam(value)
                            if active:
                                # Only one clip can be actively connected in a standard layer.
                                for k in list(self.feedback_clips):
                                    if k[0]==layer and k[1]!=column:self.feedback_clips[k]=(False,now)
                            self.feedback_clips[(layer,column)]=(active,now);self.push_live({'clip':{'layer':layer,'column':column,'active':active}})
                        elif addr in (fx.get('address') for fx in self.preset.get('fx',{}).values()):
                            self.feedback_fx[addr]=(value,now);self.push_live({'fx':{'address':addr,'value':value}})
        s.close()

    def push_live(self,event):
        # Caller owns self.lock; Condition uses the same reentrant lock.
        self.live_seq+=1;self.last_live_event=event;self.live_cv.notify_all()

    def effective_snapshot(self):
        with self.lock:
            if self.snapshot is None:return None
            # Shallow copy only changed layers; do not mutate the stored REST snapshot.
            comp=dict(self.snapshot);now=time.monotonic()
            if self.feedback_bpm is not None and now-self.feedback_bpm_at<10:
                comp['bpm']=self.feedback_bpm
            if self.feedback_blackout is not None and now-self.feedback_blackout_at<10:
                comp['bypassed']=self.feedback_blackout
            if self.feedback_master is not None and now-self.feedback_master_at<10:
                comp['master_opacity']=self.feedback_master
            if self.feedback_clips:
                rows=list(comp['layers']);updated={}
                for (l,c),(active,ts) in self.feedback_clips.items():
                    if not 1<=l<=len(rows):continue
                    row=rows[l-1]
                    if not 1<=c<=len(row['clips']):continue
                    # REST connected is authoritative after its next few refreshes;
                    # recent OSC wins during short REST propagation delay.
                    if now-ts>3 and row['clips'][c-1].get('active_known'):continue
                    if l not in updated:
                        row=dict(row);row['clips']=list(row['clips']);rows[l-1]=row;updated[l]=True
                    row['clips'][c-1]={**row['clips'][c-1],'active':active}
                comp['layers']=rows
            return comp

    def rest(self,method,path):
        host=self.config['resolume_host'];port=self.config['resolume_api_port']
        url=f'http://{host}:{port}/api/v1{path}'
        req=Request(url,method=method,headers={'Accept':'application/json','Content-Type':'application/json'})
        with urlopen(req,timeout=1.6) as r:
            blob=r.read(16000000)
            return json.loads(blob) if blob else {}

    def poll(self):
        while True:
            try:
                raw=self.rest('GET','/composition')
                snap=normalize_comp(raw)
                with self.lock:
                    if self.snapshot and snap.get('selected_deck')!=self.snapshot.get('selected_deck'):
                        self.feedback_clips.clear()
                    self.snapshot=snap;self.last_sync=time.time();self.last_error=''
            except (ValueError,TypeError,KeyError,URLError,HTTPError,OSError) as exc:
                with self.lock:self.snapshot=None;self.last_error=str(exc)[:180]
            time.sleep(max(.6,float(self.config.get('poll_interval',1.2))))

    def state(self):
        with self.lock:
            alive=self.snapshot is not None and time.time()-self.last_sync<7
            return {'version':'3.0.1','api_connected':alive,'osc_available':True,
                'composition':self.effective_snapshot() if alive else demo_comp(self.config),
                'preset':self.preset,'config':self.config,'blackout':self.blackout,
                'fx_feedback':{k:v[0] for k,v in self.feedback_fx.items() if time.monotonic()-v[1]<10},
                'feedback_ready':self.feedback_ready,'last_error':self.last_error if not alive else ''}

    def save_preset(self,data):
        p=valid_preset(data)
        temp=PRESET_PATH.with_suffix('.tmp');temp.write_text(json.dumps(p,indent=2,ensure_ascii=False),'utf-8');temp.replace(PRESET_PATH)
        with self.lock:self.preset=p
        return p

    def save_config(self,data):
        with self.lock:
            for k,v in data.items():
                if k not in DEFAULT or k=='web_port':raise ValueError('Field konfigurasi tidak boleh diubah dari UI')
                if k=='resolume_host':
                    if not isinstance(v,str) or not re.fullmatch(r'[A-Za-z0-9.:-]{1,253}',v):raise ValueError('Host tidak valid')
                elif k in ('resolume_api_port','osc_port','osc_feedback_port'):v=clampint(v,1,65535)
                elif k in ('manual_layers','manual_columns','manual_decks','manual_groups'):v=clampint(v,1,400 if k=='manual_columns' else 128)
                elif k=='transport' and v not in ('osc','midi','both'):raise ValueError('Transport tidak valid')
                elif k=='midi_output' and (not isinstance(v,str) or len(v)>160):raise ValueError('Port MIDI tidak valid')
                elif k=='poll_interval':v=rangefloat(v,.6,15)
                self.config[k]=v
            CONFIG_PATH.write_text(json.dumps(self.config,indent=2),'utf-8')
        return self.config

    def send_osc(self,address,values):
        packet=osc_packet(address,values)
        self.udp.sendto(packet,(self.config['resolume_host'],self.config['osc_port']))

    def midi_ports(self):
        try:
            import mido
            return mido.get_output_names()
        except Exception:return []

    def send_midi(self,typ,n,value,phase):
        import mido
        name=self.config['midi_output']
        if not name:raise ValueError('Pilih MIDI port pada Settings')
        with self.lock:
            if self.midi_name!=name or not self.midi:
                if self.midi:self.midi.close()
                self.midi=mido.open_output(name);self.midi_name=name
            if typ=='cc':self.midi.send(mido.Message('control_change',channel=0,control=n,value=round(value*127)));return
            if phase=='release':
                self.midi.send(mido.Message('note_off',channel=0,note=n,velocity=0));self.held.discard(n)
                t=self.timers.pop(n,None)
                if t:t.cancel()
            else:
                self.midi.send(mido.Message('note_on',channel=0,note=n,velocity=127));self.held.add(n)
                t=self.timers.pop(n,None)
                if t:t.cancel()
                t=threading.Timer(20 if phase=='press' else .09,lambda:self.send_midi('note',n,0,'release'))
                t.daemon=True;t.start();self.timers[n]=t

    def trigger(self,address,phase):
        self.send_osc(address,[0 if phase=='release' else 1])
        if phase=='pulse':
            t=threading.Timer(.065,lambda:self.send_osc(address,[0]));t.daemon=True;t.start()

    def midi_note_for(self,kind,layer,column,deck):
        # Fixed 8x8 compatibility bank. Grid outside bank is OSC-only unless custom mapped.
        if kind=='clip' and layer<=8 and column<=8:return 36+(layer-1)*8+(column-1)
        if kind=='column' and column<=8:return 99+column
        if kind=='clear' and layer<=8:return 107+layer
        if kind=='deck' and deck<=8:return 119+deck
        return None

    def action(self,v):
        if not isinstance(v,dict):raise ValueError('Action tidak valid')
        kind=v.get('action');phase=v.get('phase','pulse')
        if phase not in ('pulse','press','release'):raise ValueError('Fase tidak valid')
        l=clampint(v.get('layer',1),1,128);c=clampint(v.get('column',1),1,10000)
        d=clampint(v.get('deck',1),1,1024);g=clampint(v.get('group',1),1,1024)
        # dispatch REST to known-safe /connect, /select and /clear endpoints, OSC fallback.
        targets={
            'clip':(f'/composition/layers/{l}/clips/{c}/connect',f'/composition/layers/{l}/clips/{c}/connect'),
            'column':(f'/composition/columns/{c}/connect',f'/composition/columns/{c}/connect'),
            'deck':(f'/composition/decks/{d}/select',f'/composition/decks/{d}/select'),
            'clear':(f'/composition/layers/{l}/clear',f'/composition/layers/{l}/clear'),
            'groupclear':(f'/composition/layergroups/{g}/clear',None),
        }
        if kind in targets:
            path,osc=targets[kind]
            midi_note=self.midi_note_for(kind,l,c,d)
            mode=self.config['transport']
            if mode in ('midi','both') and midi_note is not None and self.config['midi_output']:
                try:
                    self.send_midi('note',midi_note,1,phase)
                    if mode=='midi':return {'ok':True,'via':'MIDI','confirmed':False}
                except (ImportError,ValueError,OSError) as exc:
                    if mode=='midi':raise ValueError('MIDI tidak tersedia: '+str(exc))
                    LOG.warning('MIDI tidak tersedia: %s',exc)
            if phase=='release' and kind!='clip':return {'ok':True,'via':'ignored'}
            if phase=='press' or phase=='release':
                if kind!='clip':return {'ok':True,'via':'ignored'}
                self.trigger(osc,phase);return {'ok':True,'via':'OSC','confirmed':False}
            if self.snapshot:
                try:self.rest('POST',path);return {'ok':True,'via':'Resolume REST','confirmed':False}
                except (HTTPError,URLError,OSError,ValueError):pass
            if not osc:raise ValueError('Group clear membutuhkan Resolume REST API aktif')
            self.trigger(osc,'pulse')
            return {'ok':True,'via':'OSC','confirmed':False}
        addr=None;values=[];trig=False;midi=None
        if kind=='opacity':addr=f'/composition/layers/{l}/video/opacity';values=[rangefloat(v.get('value'),0,1)];midi=('cc',19+l,values[0]) if l<=8 else None
        elif kind=='master':addr='/composition/video/opacity';values=[rangefloat(v.get('value'),0,1)];midi=('cc',30,values[0])
        elif kind=='speed':addr=f'/composition/layers/{l}/speed';values=[rangefloat(v.get('value'),0,5)]
        elif kind=='volume':addr=f'/composition/layers/{l}/audio/volume';values=[rangefloat(v.get('value'),0,1)]
        elif kind=='transition':addr=f'/composition/layers/{l}/transition/duration';values=[rangefloat(v.get('value'),0,10)]
        elif kind=='transitionmode':
            name=v.get('name')
            if not isinstance(name,str) or not re.fullmatch(r'[\w -]{1,50}',name):raise ValueError('Nama transition tidak valid')
            addr=f'/composition/layers/{l}/video/transition/mixer/blendmode';values=[name]
        elif kind=='crossfader':addr='/composition/crossfader/phase';values=[rangefloat(v.get('value'),0,1)*2-1];midi=('cc',31,(values[0]+1)/2)
        elif kind=='blackout':
            if type(v.get('enabled')) is not bool:raise ValueError('Blackout harus boolean')
            enabled=v['enabled']
            # Dedicated master opacity blackout. Restore the level from before blackout,
            # rather than forcing the master to 100% and destroying the VJ mix setting.
            with self.lock:
                if enabled and not self.blackout:
                    snap=self.effective_snapshot()
                    last=snap.get('master_opacity') if snap else None
                    self.blackout_master=last if type(last) in (float,int) and 0.01<=last<=1 else 1.0
                restore=self.blackout_master
            addr='/composition/video/opacity';values=[0.0 if enabled else float(restore)]
            self.send_osc(addr,values)
            with self.lock:self.blackout=enabled;self.feedback_master=values[0];self.feedback_master_at=time.monotonic()
            return {'ok':True,'via':'OSC','address':addr,'enabled':enabled,'confirmed':False}
        elif kind=='tap':addr='/composition/tempocontroller/tempotap';trig=True
        elif kind=='tempo':addr='/composition/tempocontroller/tempo';values=[rangefloat(v.get('value'),20,300)]
        elif kind=='macro':
            n=clampint(v.get('index'),1,8);addr=f'/composition/dashboard/link{n}';values=[rangefloat(v.get('value',1),0,1)];midi=('cc',39+n,values[0])
        elif kind=='raw':
            addr=v.get('address');value=v.get('value',1)
            if type(value) in (float,int) and -1e6<=value<=1e6:values=[value]
            elif isinstance(value,str) and len(value)<101:values=[value]
            else:raise ValueError('Nilai OSC invalid')
            trig=bool(v.get('trigger',False))
        else:raise ValueError('Perintah tidak dikenal')
        if trig:self.trigger(addr,phase)
        elif phase!='release':self.send_osc(addr,values)
        if self.config['transport'] in ('midi','both') and midi and midi[1]<128:
            try:self.send_midi(*midi,'pulse')
            except (ImportError,ValueError) as e:LOG.warning('MIDI gagal: %s',e)
        return {'ok':True,'via':'OSC','address':addr,'confirmed':False}

PULSE=None
class Handler(BaseHTTPRequestHandler):
    server_version='PulseArena/3.0.1';protocol_version='HTTP/1.1'
    def log_message(self,fmt,*args):LOG.info('%s %s',self.address_string(),fmt%args)
    def respond(self,obj,code=200,headers=None):
        data=json.dumps(obj,ensure_ascii=False).encode('utf-8')
        self.send_response(code);self.send_header('Content-Type','application/json; charset=utf-8');self.send_header('Cache-Control','no-store')
        self.send_header('X-Content-Type-Options','nosniff');self.send_header('Content-Length',str(len(data)))
        for k,v in (headers or {}).items():self.send_header(k,v)
        self.end_headers();self.wfile.write(data)
    def authed(self):
        try:
            cookie=SimpleCookie(self.headers.get('Cookie',''));token=cookie.get('pulse_session')
            return bool(token and PULSE.sessions.get(token.value,0)>time.time())
        except Exception:return False
    def origin_ok(self):
        origin=self.headers.get('Origin')
        if not origin:return True
        parsed=urlsplit(origin)
        return parsed.scheme=='http' and parsed.netloc==self.headers.get('Host')
    def body(self):
        n=clampint(self.headers.get('Content-Length','0'),0,1048576)
        obj=json.loads(self.rfile.read(n))
        if not isinstance(obj,dict):raise ValueError('Body harus object')
        return obj
    def events(self):
        """Authenticated SSE for low-latency OSC feedback, with HTTP poll as fallback."""
        self.send_response(200)
        self.send_header('Content-Type','text/event-stream; charset=utf-8')
        self.send_header('Cache-Control','no-store, no-transform')
        self.send_header('X-Accel-Buffering','no')
        self.send_header('Connection','keep-alive')
        self.end_headers()
        last=-1
        try:
            self.wfile.write(b': connected\n\n');self.wfile.flush()
            while self.authed():
                with PULSE.lock:
                    PULSE.live_cv.wait_for(lambda:PULSE.live_seq!=last,timeout=12)
                    seq=PULSE.live_seq;payload=PULSE.last_live_event.copy()
                if seq!=last and payload:
                    self.wfile.write(('data: '+json.dumps(payload,separators=(',',':'))+'\n\n').encode('utf-8'))
                    last=seq
                else:
                    self.wfile.write(b': ping\n\n')
                last=seq
                self.wfile.flush()
        except (BrokenPipeError,ConnectionResetError,OSError):pass

    def do_GET(self):
        path=urlsplit(self.path).path
        if path=='/api/session':return self.respond({'authenticated':self.authed(),'version':'3.0.1'})
        if path.startswith('/api/'):
            if not self.authed():return self.respond({'error':'Masukkan PIN'},401)
            if path=='/api/events':return self.events()
            if path=='/api/state':return self.respond(PULSE.state())
            if path=='/api/ports':return self.respond({'ports':PULSE.midi_ports()})
            return self.respond({'error':'Endpoint tidak tersedia'},404)
        files={'/':'index.html','/index.html':'index.html','/app.js':'app.js','/style.css':'style.css',
               '/icon.svg':'icon.svg','/manifest.webmanifest':'manifest.webmanifest'}
        name=files.get(path)
        if not name:return self.send_error(404)
        try:blob=(STATIC/name).read_bytes()
        except OSError:return self.send_error(404)
        self.send_response(200);self.send_header('Content-Type',mimetypes.guess_type(name)[0] or 'application/octet-stream')
        self.send_header('Content-Length',str(len(blob)));self.send_header('Cache-Control','no-store');self.send_header('X-Content-Type-Options','nosniff')
        self.end_headers();self.wfile.write(blob)
    def do_POST(self):
        path=urlsplit(self.path).path
        if not self.origin_ok():return self.respond({'error':'Origin tidak sesuai'},403)
        if path!='/api/login' and not self.authed():return self.respond({'error':'Sesi berakhir'},401)
        try:
            data=self.body()
            if path=='/api/login':
                key=self.client_address[0];hist=PULSE.failures[key];now=time.time()
                while hist and hist[0]<now-60:hist.popleft()
                if len(hist)>=10:return self.respond({'error':'Terlalu banyak percobaan'},429)
                if not hmac.compare_digest(str(data.get('pin','')),PULSE.pin):hist.append(now);return self.respond({'error':'PIN salah'},401)
                hist.clear();token=secrets.token_urlsafe(32);PULSE.sessions[token]=now+43200
                return self.respond({'ok':True},headers={'Set-Cookie':f'pulse_session={token}; HttpOnly; SameSite=Strict; Path=/; Max-Age=43200'})
            if path=='/api/action':return self.respond(PULSE.action(data))
            if path=='/api/preset':return self.respond({'ok':True,'preset':PULSE.save_preset(data)})
            if path=='/api/config':return self.respond({'ok':True,'config':PULSE.save_config(data)})
            if path=='/api/logout':
                try:
                    cookies=SimpleCookie(self.headers.get('Cookie',''));c=cookies.get('pulse_session')
                    if c:PULSE.sessions.pop(c.value,None)
                except Exception:pass
                return self.respond({'ok':True},headers={'Set-Cookie':'pulse_session=; Max-Age=0; Path=/; HttpOnly; SameSite=Strict'})
            return self.respond({'error':'Endpoint tidak tersedia'},404)
        except (ValueError,TypeError,KeyError,json.JSONDecodeError) as exc:return self.respond({'error':str(exc)},400)
        except (OSError,ConnectionError) as exc:LOG.exception('Request gagal');return self.respond({'error':'I/O gagal'},500)

def local_ips():
    found=[]
    try:
        for a in socket.getaddrinfo(socket.gethostname(),None,socket.AF_INET):
            ip=a[4][0]
            if not ip.startswith('127.') and ip not in found:found.append(ip)
    except OSError:pass
    try:
        s=socket.socket(socket.AF_INET,socket.SOCK_DGRAM);s.connect(('192.0.2.1',80));ip=s.getsockname()[0];s.close()
        if ip not in found:found.append(ip)
    except OSError:pass
    return found

def main():
    global PULSE
    logging.basicConfig(level=logging.INFO,format='%(asctime)s %(message)s',datefmt='%H:%M:%S')
    PULSE=Pulse()
    print('\n'+'='*61+'\n  PULSE ARENA v3.0.1 — PROFESSIONAL LIVE CONTROLLER\n'+'='*61)
    print('  PIN:',PULSE.pin,'\n  PC : http://127.0.0.1:'+str(PULSE.config['web_port']))
    for ip in local_ips():print('  HP : http://%s:%d'%(ip,PULSE.config['web_port']))
    print('  Resolume OSC Input:7000 | Webserver REST:8080\n  CTRL+C untuk berhenti.\n')
    server=ThreadingHTTPServer(('0.0.0.0',PULSE.config['web_port']),Handler);server.daemon_threads=True
    try:server.serve_forever()
    except KeyboardInterrupt:pass
    finally:server.server_close();PULSE.udp.close()
if __name__=='__main__':main()
