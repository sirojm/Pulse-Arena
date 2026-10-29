import unittest,sys,time,threading,http.client
from pathlib import Path
from unittest.mock import patch
from http.server import ThreadingHTTPServer
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import server

class TestStream(unittest.TestCase):
    def test_authenticated_sse_push(self):
        with patch.object(server.Pulse,'poll',lambda _:None),patch.object(server.Pulse,'listen_feedback',lambda _:None):
            pulse=server.Pulse()
        server.PULSE=pulse
        pulse.sessions['testtoken']=time.time()+100
        srv=ThreadingHTTPServer(('127.0.0.1',0),server.Handler)
        th=threading.Thread(target=srv.serve_forever,daemon=True);th.start()
        conn=http.client.HTTPConnection('127.0.0.1',srv.server_port,timeout=3)
        try:
            conn.request('GET','/api/events',headers={'Cookie':'pulse_session=testtoken'})
            res=conn.getresponse()
            self.assertEqual(res.status,200)
            self.assertEqual(res.readline(),b': connected\n')
            res.readline()
            res.readline() # initial : ping
            res.readline()
            with pulse.lock:pulse.push_live({'bpm':142.5})
            line=res.readline()
            self.assertIn(b'"bpm":142.5',line)
        finally:conn.close();srv.shutdown();srv.server_close();pulse.udp.close()
