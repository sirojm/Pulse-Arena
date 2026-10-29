import unittest,sys,struct,socket,time
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import server

def unit_pulse():
    with patch.object(server.Pulse,'poll',lambda _:None),patch.object(server.Pulse,'listen_feedback',lambda _:None):
        return server.Pulse()

class TestV32(unittest.TestCase):
    def test_parse_osc_feedback_and_bundle(self):
        pkt=server.osc_packet('/composition/tempocontroller/tempo',[142.5])
        self.assertEqual(list(server.parse_osc_messages(pkt)),[('/composition/tempocontroller/tempo',[142.5])])
        pkt2=server.osc_packet('/composition/layers/3/clips/8/connected',[1])
        pack=b'#bundle\0'+b'\0'*8+struct.pack('>i',len(pkt))+pkt+struct.pack('>i',len(pkt2))+pkt2
        self.assertEqual(len(list(server.parse_osc_messages(pack))),2)
        self.assertEqual(list(server.parse_osc_messages(b'not OSC')),[])
    def test_bpm_normalization_does_not_invent_128(self):
        self.assertIsNone(server.normalize_comp({'layers':[]})['bpm'])
        self.assertEqual(server.normalize_comp({'tempocontroller':{'tempo':{'value':154}}})['bpm'],154)
    def test_valid_macro_config_and_reject_bad(self):
        cfg={'fx':{'2':{'label':'Strobe','address':'/composition/dashboard/link2','mode':'toggle','on':1,'off':0,'color':'#123456'}}}
        self.assertEqual(server.valid_preset(cfg)['fx']['2']['mode'],'toggle')
        cfg['fx']['2']['mode']='not a mode'
        with self.assertRaises(ValueError):server.valid_preset(cfg)
    def test_blackout_master_preserves_level(self):
        capture=socket.socket(socket.AF_INET,socket.SOCK_DGRAM)
        capture.bind(('127.0.0.1',0));capture.settimeout(1)
        try:
            pulse=unit_pulse();pulse.config['osc_port']=capture.getsockname()[1]
            pulse.snapshot=server.normalize_comp({'layers':[],'video':{'opacity':{'value':0.63}}})
            pulse.last_sync=time.time()
            self.assertEqual(pulse.action({'action':'blackout','enabled':True})['enabled'],True)
            packet,_=capture.recvfrom(4096)
            self.assertEqual(list(server.parse_osc_messages(packet))[0],('/composition/video/opacity',[0.0]))
            pulse.action({'action':'blackout','enabled':False})
            packet,_=capture.recvfrom(4096)
            self.assertAlmostEqual(list(server.parse_osc_messages(packet))[0][1][0],.63,places=3)
        finally:capture.close()
    def test_rest_connected_clip_glows_until_explicit_disconnection(self):
        pulse=unit_pulse()
        pulse.snapshot=server.normalize_comp({'layers':[{'clips':[{'name':'INTRO','connected':{'value':True}}]}], 'columns':[{}]})
        self.assertTrue(pulse.effective_snapshot()['layers'][0]['clips'][0]['active'])
        pulse.snapshot=server.normalize_comp({'layers':[{'clips':[{'name':'INTRO','connected':{'value':False}}]}],'columns':[{}]})
        self.assertFalse(pulse.effective_snapshot()['layers'][0]['clips'][0]['active'])
    def test_osc_clip_status_override_persists_until_off(self):
        pulse=unit_pulse()
        pulse.snapshot=server.normalize_comp({'layers':[{'clips':[{'name':'INTRO'}]}],'columns':[{}]})
        pulse.feedback_clips[(1,1)]=(True,time.monotonic()-900)
        self.assertTrue(pulse.effective_snapshot()['layers'][0]['clips'][0]['active'])
        pulse.feedback_clips[(1,1)]=(False,time.monotonic())
        self.assertFalse(pulse.effective_snapshot()['layers'][0]['clips'][0]['active'])

if __name__=='__main__':unittest.main()
