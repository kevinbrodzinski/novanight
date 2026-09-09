import io, json, os, threading, time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import paramiko

STATE={"phase":"init","ok":False,"output":"","started_at":time.time()}

def bootstrap():
    global STATE
    host=os.environ["SSH_HOST"]
    key_text=os.environ["SSH_KEY"]
    user=os.environ.get("SSH_USER","root")
    cmd=r'''set -euo pipefail
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
for i in $(seq 1 60); do
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
echo 'CARRIER_HTTP_TIMEOUT'
docker ps -a --filter name=dusb04-carrier
docker logs --tail 120 dusb04-carrier || true
exit 42
'''
    try:
        STATE={"phase":"connecting","ok":False,"output":"","started_at":STATE["started_at"]}
        key=paramiko.Ed25519Key.from_private_key(io.StringIO(key_text))
        c=paramiko.SSHClient(); c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        c.connect(hostname=host, username=user, pkey=key, timeout=20, banner_timeout=20, auth_timeout=20)
        STATE["phase"]="bootstrapping"
        stdin, stdout, stderr=c.exec_command("bash -lc "+json.dumps(cmd), timeout=900)
        out=stdout.read().decode("utf-8","replace")
        err=stderr.read().decode("utf-8","replace")
        rc=stdout.channel.recv_exit_status()
        c.close()
        STATE={"phase":"done","ok":rc==0,"rc":rc,"output":out,"stderr":err,"started_at":STATE["started_at"],"finished_at":time.time()}
    except Exception as e:
        STATE={"phase":"error","ok":False,"error":repr(e),"output":STATE.get("output",""),"started_at":STATE["started_at"],"finished_at":time.time()}

class H(BaseHTTPRequestHandler):
    def do_GET(self):
        body=json.dumps(STATE,sort_keys=True).encode()
        self.send_response(200); self.send_header("content-type","application/json"); self.send_header("content-length",str(len(body))); self.end_headers(); self.wfile.write(body)
    def log_message(self,*args): pass

threading.Thread(target=bootstrap,daemon=True).start()
ThreadingHTTPServer(("0.0.0.0",int(os.environ.get("PORT","10000"))),H).serve_forever()
