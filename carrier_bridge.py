#!/usr/bin/env python3
import http.client, os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
UP_HOST=os.getenv('DUSB04_UPSTREAM_HOST','127.0.0.1')
UP_PORT=int(os.getenv('DUSB04_UPSTREAM_PORT','8080'))
LISTEN=int(os.getenv('PORT','9091'))
class H(BaseHTTPRequestHandler):
    protocol_version='HTTP/1.1'
    def _go(self):
        body=b''; n=self.headers.get('content-length')
        if n: body=self.rfile.read(int(n))
        c=http.client.HTTPConnection(UP_HOST,UP_PORT,timeout=20)
        headers={k:v for k,v in self.headers.items() if k.lower() not in {'host','connection','content-length','transfer-encoding'}}
        if body: headers['Content-Length']=str(len(body))
        try:
            c.request(self.command,self.path,body=body,headers=headers); r=c.getresponse(); data=r.read()
            self.send_response(r.status)
            for k,v in r.getheaders():
                if k.lower() not in {'connection','transfer-encoding','content-length'}: self.send_header(k,v)
            self.send_header('Content-Length',str(len(data))); self.end_headers()
            if self.command!='HEAD': self.wfile.write(data)
        except Exception as e:
            data=("bridge upstream error: "+repr(e)).encode(); self.send_response(502); self.send_header('Content-Type','text/plain'); self.send_header('Content-Length',str(len(data))); self.end_headers(); self.wfile.write(data)
        finally: c.close()
    do_GET=_go; do_POST=_go; do_PUT=_go; do_DELETE=_go; do_PATCH=_go; do_HEAD=_go
    def log_message(self,fmt,*args): print('DUSB04_BRIDGE',self.address_string(),fmt%args,flush=True)
ThreadingHTTPServer(('0.0.0.0',LISTEN),H).serve_forever()
