import json, os, subprocess, threading, time, urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
KEYDIR='/tmp/dusb04-agent2'; PRIV=KEYDIR+'/id_ed25519'; PUB=PRIV+'.pub'
os.makedirs(KEYDIR,exist_ok=True)
if not os.path.exists(PRIV): subprocess.run(['ssh-keygen','-q','-t','ed25519','-N','','-f',PRIV,'-C','dusb04-campaign-agent-v2'],check=True)
STATE={}; LOCK=threading.Lock()

SCRIPTS={
'carrier':r'''set -euo pipefail
cloud-init status --wait || true
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get install -y -qq docker.io curl
systemctl enable --now docker
docker rm -f dusb04-carrier-probe >/dev/null 2>&1 || true
docker pull nginx:alpine >/tmp/dusb04_pull.txt
docker run -d --name dusb04-carrier-probe -p 80:80 nginx:alpine >/tmp/dusb04_cid
for i in $(seq 1 30); do c=$(curl -sS -o /tmp/dusb04_nginx -w '%{http_code}' --max-time 2 http://127.0.0.1/ || true); if [ "$c" = "200" ]; then break; fi; sleep 1; done
echo "DOCKER=$(docker --version)"; echo "LOCAL_HTTP=$c"; echo -n 'BODY_SHA256='; sha256sum /tmp/dusb04_nginx | awk '{print $1}'; docker ps --filter name=dusb04-carrier-probe --format 'CONTAINER={{.ID}} STATUS={{.Status}} PORTS={{.Ports}}'
[ "$c" = "200" ]
''',
'restgym_setup':r'''set -euo pipefail
systemctl is-active --quiet docker
for spec in 'scs restgym/scs-api:1.0.0 18081' 'person restgym/person-controller-api:1.0.0 18082' 'market restgym/market-api:1.0.0 18083'; do
  set -- $spec; n=$1; img=$2; p=$3; docker pull "$img" >/tmp/pull_$n.txt; docker rm -f "dusb04-$n" >/dev/null 2>&1 || true; docker run -d --name "dusb04-$n" -e TOOL=DUSB04 -e RUN="$n" -p "$p:9090" "$img" >/tmp/cid_$n; done
sleep 45
for spec in 'scs 18081' 'person 18082' 'market 18083'; do set -- $spec; n=$1; p=$2; c=$(curl -sS -o "/tmp/body_$n" -w '%{http_code}' --max-time 3 "http://127.0.0.1:$p/error" || true); echo "TARGET=$n STATUS=$c"; if [ -f "/tmp/body_$n" ]; then echo -n "BODY_SHA256_$n="; sha256sum "/tmp/body_$n" | awk '{print $1}'; fi; docker ps -a --filter name="dusb04-$n" --format 'CONTAINER={{.ID}} STATUS={{.Status}} PORTS={{.Ports}}'; echo "LOGTAIL_$n"; docker logs --tail 25 "dusb04-$n" 2>&1 || true; done
''',
'diagnose':r'''set -euo pipefail
for spec in 'scs restgym/scs-api:1.0.0' 'person restgym/person-controller-api:1.0.0' 'market restgym/market-api:1.0.0'; do
  set -- $spec; n=$1; img=$2
  echo "=== $n IMAGE CONFIG ==="
  docker image inspect "$img" --format 'ENTRYPOINT={{json .Config.Entrypoint}} CMD={{json .Config.Cmd}} EXPOSED={{json .Config.ExposedPorts}} ENV={{json .Config.Env}}'
  echo "=== $n FILES ==="
  docker run --rm --entrypoint /bin/sh "$img" -lc 'printf "PID1 candidates:\n"; ls -la /api 2>/dev/null || true; ls -la /infrastructure 2>/dev/null || true; find /api -maxdepth 2 -type f 2>/dev/null | head -80; printf "scripts:\n"; find / -maxdepth 3 \( -name "*.sh" -o -name "entrypoint*" \) 2>/dev/null | head -80' || true
  echo "=== $n RUN STATE ==="
  docker inspect "dusb04-$n" --format 'STATE={{json .State}} CONFIG={{json .Config}}' 2>/dev/null || true
  echo "=== $n PROC ==="
  docker top "dusb04-$n" -eo pid,ppid,args 2>/dev/null || true
  echo "=== $n PORTS ==="
  docker exec "dusb04-$n" /bin/sh -lc 'command -v ss >/dev/null && ss -lntp || (command -v netstat >/dev/null && netstat -lntp) || true; ps -ef' 2>/dev/null || true
  echo "=== $n LOGS ==="
  docker logs --tail 120 "dusb04-$n" 2>&1 || true
done
''',
'cleanup':r'''set -euo pipefail
for n in dusb04-carrier-probe dusb04-scs dusb04-person dusb04-market; do docker rm -f "$n" >/dev/null 2>&1 || true; done
echo CLEANED
'''
}

def run_mode(host,mode):
    global STATE
    with LOCK:
        STATE[mode]={'phase':'running','host':host,'started_at':time.time()}
    try:
        cp=subprocess.run(['ssh','-o','StrictHostKeyChecking=no','-o','UserKnownHostsFile=/dev/null','-o','ConnectTimeout=20','-i',PRIV,'root@'+host,'bash -s'],input=SCRIPTS[mode],text=True,capture_output=True,timeout=900)
        STATE[mode]={'phase':'done','ok':cp.returncode==0,'rc':cp.returncode,'host':host,'started_at':STATE[mode]['started_at'],'finished_at':time.time(),'output':cp.stdout[-50000:],'stderr':cp.stderr[-12000:]}
    except Exception as e: STATE[mode]={'phase':'error','ok':False,'host':host,'error':repr(e),'finished_at':time.time()}

class H(BaseHTTPRequestHandler):
    def do_GET(self):
        u=urllib.parse.urlparse(self.path); q=urllib.parse.parse_qs(u.query)
        if u.path=='/pubkey': body=open(PUB,'rb').read(); typ='text/plain'
        elif u.path=='/run':
            host=q.get('host',[''])[0]; mode=q.get('mode',[''])[0]
            if not host or mode not in SCRIPTS: self.send_response(400); self.end_headers(); return
            threading.Thread(target=run_mode,args=(host,mode),daemon=True).start(); body=json.dumps({'started':True,'host':host,'mode':mode}).encode(); typ='application/json'
        elif u.path=='/status': body=json.dumps(STATE,sort_keys=True).encode(); typ='application/json'
        else: body=json.dumps({'modes':list(SCRIPTS),'paths':['/pubkey','/run?host=IP&mode=carrier','/status']}).encode(); typ='application/json'
        self.send_response(200); self.send_header('content-type',typ); self.send_header('content-length',str(len(body))); self.end_headers(); self.wfile.write(body)
    def log_message(self,*a): pass
ThreadingHTTPServer(('0.0.0.0',int(os.environ.get('PORT','10000'))),H).serve_forever()
