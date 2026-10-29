import unittest,sys,struct, tempfile,threading,time,json,socket
from pathlib import Path
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import server

class TestCore(unittest.TestCase):
    def test_osc_packet_trigger(self):
        blob=server.osc_packet('/composition/layers/1/clips/1/connect',[1])
        self.assertTrue(blob.startswith(b'/composition/layers/1/clips/1/connect\0'))
        self.assertIn(b',i\0',blob)
        self.assertEqual(blob[-4:],struct.pack('>i',1))
    def test_osc_bad_address(self):
        for address in ('../../bad','/has space','/x;rm'):
            with self.assertRaises(ValueError):server.osc_packet(address,[1])
    def test_big_composition(self):
        raw={'name':{'value':'MY SHOW'},'decks':[{'name':{'value':'DROP'},'selected':{'value':True}}],
            'columns':[{'name':{'value':f'Column {i}'}} for i in range(100)],
            'layers':[{'id':100+i,'name':{'value':f'Layer {i}'},'clips':[{'name':{'value':f'clip {j}'},'connected':{'value':j==2}} for j in range(100)]} for i in range(20)],
            'layergroups':[{'name':{'value':'Main'}}]}
        comp=server.normalize_comp(raw)
        self.assertEqual(len(comp['layers']),20)
        self.assertEqual(len(comp['columns']),100)
        self.assertEqual(len(comp['layers'][0]['clips']),100)
        self.assertTrue(comp['layers'][0]['clips'][2]['active'])
        self.assertEqual(comp['selected_deck'],1)
    def test_empty_clips(self):
        raw={'layers':[{'clips':[{'id':99,'name':''},{'id':100,'name':'Test'}]}], 'columns':[{},{}]}
        comp=server.normalize_comp(raw)
        self.assertFalse(comp['layers'][0]['clips'][0]['filled'])
        self.assertTrue(comp['layers'][0]['clips'][1]['filled'])
    def test_valid_preset(self):
        p=server.valid_preset({'pads':{'d1:l7:c70':{'label':'Hallo 🌴\nمرحبا','color':'#aabbcc','trigger':'piano','osc':'/composition/dashboard/link1'}}})
        self.assertEqual(p['pads']['d1:l7:c70']['trigger'],'piano')
        with self.assertRaises(ValueError):server.valid_preset({'pads':{'d1:l1:c1':{'label':'x','color':'red'}}})
    def test_bounded_config_and_invalid_action(self):
        with self.assertRaises(ValueError):server.clampint(0,1,100)
        with self.assertRaises(ValueError):server.osc_packet('/x',[object()])
    def test_demo_dimensions(self):
        c=dict(server.DEFAULT);c['manual_layers']=25;c['manual_columns']=130
        s=server.demo_comp(c)
        self.assertEqual(len(s['layers']),25)
        self.assertEqual(len(s['columns']),130)
    def test_midi_mapping(self):
        p=server.Pulse()
        self.assertEqual(p.midi_note_for('clip',1,1,1),36)
        self.assertEqual(p.midi_note_for('clip',8,8,1),99)
        self.assertIsNone(p.midi_note_for('clip',12,12,1))
        self.assertEqual(p.midi_note_for('deck',1,1,8),127)
    def test_udp_action_to_capture(self):
        capture=socket.socket(socket.AF_INET,socket.SOCK_DGRAM);capture.bind(('127.0.0.1',0));capture.settimeout(2)
        p=server.Pulse();p.config['osc_port']=capture.getsockname()[1]
        p.action({'action':'clip','layer':12,'column':65})
        packet,_=capture.recvfrom(4096)
        self.assertIn(b'/layers/12/clips/65/connect',packet)
        capture.close()

if __name__=='__main__':unittest.main()
