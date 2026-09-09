import json, os, subprocess, threading, time, urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

KEYDIR='/tmp/dusb04-ssh'
PRIV=KEYDIR+'/id_ed25519'
PUB=PRIV+'.pub'
os.makedirs(KEYDIR, exist_ok=True)
if not os.path.exists(PRIV):
    subprocess.run(['ssh-keygen','-q','-t','ed25519','-N','','-f',PRIV,'-C','dusb04-render-agent'], check=True)
STATE={'phase':'ready','ok':False,'output':'','stderr':''}
LOCK=threading.Lock()

BOOTSTRAP=r'''set -euo pipefail
cloud-init status --wait || true
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get install -y -qq docker.io curl
systemctl enable --now docker
printf 'DOCKER_VERSION='; docker --version
printf 'PULL='; docker pull restgym/user-management-api:1.0.0 | tail -1
printf 'IMAGE='; docker image inspect restgym/user-management-api:1.0.0 --format '{{index .RepoDigests 0}}'
docker rm -f dusb04-carrier >/dev/null 2>&1 || true
docker run -d --name dusb04-carrier -e TOOL=DUSB04_CARRIER -e RUN=carrier -p 19090:9090 restgym/user-management-api:1.0.0
for i in $(seq 1 90); do
  code=$(curl -sS -o /tmp/dusb04_body -w '%{http_code}' --max-time 3 http://127.0.0.1:19090/error || true)
  if [ "$code" != "000" ]; then
    echo "LOCAL_HTTP_STATUS=$code"
    echo -n 'LOCAL_BODY_SHA256='; sha256sum /tmp/dusb04_body | awk '{print $1}'
    echo -n 'LOCAL_BODY_PREFIX='; head -c 300 /tmp/dusb04_body | tr '\n' ' '; echo
    docker ps --filter name=dusb04-carrier --format 'CONTAINER={{.ID}} STATUS={{.Status}} PORTS={{.Ports}}'
    exit 0
  fi
  sleep 2
done
echo CARRIER_HTTP_TIMEOUT
docker ps -a --filter name=dusb04-carrier
docker logs --tail 150 dusb04-carrier || true
exit 42
'''

def run_bootstrap(host):
    global STATE
    with LOCK:
        if STATE.get('phase')=='running': return
        STATE={'phase':'running','ok':False,'host':host,'started_at':time.time(),'output':'','stderr':''}
    try:
        cp=subprocess.run(['ssh','-o','StrictHostKeyChecking=no','-o','UserKnownHostsFile=/dev/null','-o','ConnectTimeout=20','-i',PRIV,'root@'+host,'bash -s'], input=BOOTSTRAP, text=True, capture_output=True, timeout=900)
        STATE={'phase':'done','ok':cp.returncode==0,'host':host,'rc':cp.returncode,'started_at':STATE['started_at'],'finished_at':time.time(),'output':cp.stdout[-24000:],'stderr':cp.stderr[-12000:]}
    except Exception as e:
        STATE={'phase':'error','ok':False,'host':host,'error':repr(e),'started_at':STATE.get('started_at'),'finished_at':time.time(),'output':'','stderr':''}

class H(BaseHTTPRequestHandler):
    def do_GET(self):
        u=urllib.parse.urlparse(self.path); q=urllib.parse.parse_qs(u.query)
        if u.path=='/pubkey':
            body=open(PUB,'rb').read(); ctype='text/plain'
        elif u.path=='/bootstrap':
            host=q.get('host',[''])[0]
            if not host:
                self.send_response(400); self.end_headers(); return
            threading.Thread(target=run_bootstrap,args=(host,),daemon=True).start()
            body=json.dumps({'started':True,'host':host}).encode(); ctype='application/json'
        elif u.path=='/status':
            body=json.dumps(STATE,sort_keys=True).encode(); ctype='application/json'
        else:
            body=json.dumps({'paths':['/pubkey','/bootstrap?host=IP','/status']}).encode(); ctype='application/json'
        self.send_response(200); self.send_header('content-type',ctype); self.send_header('content-length',str(len(body))); self.end_headers(); self.wfile.write(body)
    def log_message(self,*args): pass

ThreadingHTTPServer(('0.0.0.0',int(os.environ.get('PORT','10000'))),H).serve_forever()
