#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
============================================================
 BIOHAZARD CTF LAB — 「生化公司」漏洞靶场
============================================================
 剧情: 你是一名白帽雇佣兵, 接悬赏入侵"生化公司"内网。
 目标: 从 Web 入口一路打通到内网域控, 收集全部 flag。

 本应用【故意】复刻以下漏洞(仅限本地靶场/CTF学习):
   1. 调试接口信息泄露      /debug_info        -> flag#1
   2. SQL 注入绕过登录      /login             -> 管理员会话
   3. Flask session 弱密钥  密钥硬编码在源码里   -> 伪造管理员 cookie
   4. SSRF                  /api/fetch         -> 访问内网 backup 服务
   5. 命令注入              /api/ping          -> RCE (低权限)
   6. pickle 反序列化       /api/deserialize   -> RCE (root)
   7. 内网横向移动           -> backup / dc      -> flag#3 flag#4

 运行模式:
   - Docker:   设置环境变量 MYSQL_HOST 后使用 MySQL (见 docker-compose.yml)
   - 本地测试: 不设置 MYSQL_HOST, 自动使用 SQLite (仅用于演示/开发)
============================================================
"""
import os
import base64
import pickle
import sqlite3
import subprocess
from functools import wraps

from flask import Flask, request, session, redirect, jsonify, Response

# ================= 配置 =================
# 💀 故意硬编码的弱密钥 (视频同款: Th1s_1s_N0t_Th3_Rea1_K3y)
SECRET_KEY = "Th1s_1s_N0t_Th3_Rea1_K3y"

MYSQL_HOST = os.environ.get("MYSQL_HOST", "")   # 留空 = SQLite 本地模式
MYSQL_USER = os.environ.get("MYSQL_USER", "corp_app")
MYSQL_PASS = os.environ.get("MYSQL_PASS", "CorpApp@2026")
MYSQL_DB   = os.environ.get("MYSQL_DB", "corp")

# ================= Flag 定义 =================
FLAG1 = "flag{0pen_D3bug_1s_D4ng3r0us}"        # /debug_info
# FLAG2 存在数据库 flags 表中 (需要通过登录后 /admin 读取)
# FLAG3 在内网 backup 服务 (SSRF 可读)
# FLAG4 在域控 dc 服务 (需要服务账号口令, 口令在 backup 里)

APP = Flask(__name__)
APP.secret_key = SECRET_KEY
APP.config["MAX_CONTENT_LENGTH"] = 1 * 1024 * 1024

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
<p>🔗 <a href='/login'>员工登录</a> · <a href='/admin'>内部后台</a> · <a href='/source'>源码</a></p>
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

# ================= 关卡1: 调试接口信息泄露 → flag#1 =================
@APP.route("/debug_info")
def debug_info():
    info = {
        "app": "BioHazard Corp Web Portal v1.4",
        "framework": "Flask",
        "flag1": FLAG1,
        # 内网信息: Docker 模式下 backup/mysql/dc 都在这个网段
        "mysql_host": (MYSQL_HOST or "127.0.0.1") + ":3306",
        "internal_subnet": os.environ.get("INTERNAL_SUBNET", "172.20.0.0/24"),
        "note": "调试接口忘了关, 建议尽快下线 :)"
    }
    return jsonify(info)

# ================= 关卡2: SQL 注入绕过登录 =================
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
        return redirect("/admin")
    return "<p style='color:red'>登录失败</p><a href='/login'>重试</a>"

# ================= 关卡3: /admin 后台 → flag#2 (需 admin 角色) =================
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

# ================= 关卡3.5: 源码泄露 → 弱密钥 =================
@APP.route("/source")
def source():
    with open(__file__, "r", encoding="utf-8") as f:
        return Response("<pre>" + f.read().replace("<", "&lt;") + "</pre>",
                        mimetype="text/html")

@APP.route("/api/routes")
def api_routes():
    routes = sorted({str(r) for r in APP.url_map.iter_rules() if "static" not in str(r)})
    return jsonify({"routes": routes,
                    "hint": "枚举路由可以发现隐藏功能点, 包括 /api/fetch /api/ping /api/deserialize"})

# ================= 关卡4: SSRF → 内网 backup 服务 =================
@APP.route("/api/fetch", methods=["GET"])
def api_fetch():
    url = request.args.get("url", "")
    if not url:
        return jsonify({"error": "缺少 url 参数", "example": "/api/fetch?url=http://backup:8080/"})
    import requests
    try:
        r = requests.get(url, timeout=4)
        # 二进制内容转 base64 展示(backup.zip 场景)
        if "text" in r.headers.get("Content-Type", ""):
            return Response(r.text[:3000], mimetype="text/plain")
        return jsonify({"base64": base64.b64encode(r.content[:1000]).decode(), "size": len(r.content)})
    except Exception as e:
        return jsonify({"error": str(e)})

# ================= 关卡5: 命令注入 → 低权限 RCE =================
@APP.route("/api/ping", methods=["GET"])
def api_ping():
    ip = request.args.get("ip", "")
    if not ip:
        return jsonify({"error": "缺少 ip 参数", "example": "/api/ping?ip=127.0.0.1",
                        "hint": "试试 ';id' 看看会发生什么"})
    # 💀 漏洞: 直接拼接 shell 命令
    cmd = f"ping -c 1 {ip}"
    try:
        out = subprocess.check_output(cmd, shell=True, stderr=subprocess.STDOUT,
                                      timeout=5).decode(errors="ignore")
        return Response(out, mimetype="text/plain")
    except subprocess.TimeoutExpired:
        return Response("timeout", mimetype="text/plain")
    except Exception as e:
        return Response(str(e), mimetype="text/plain")

# ================= 关卡6: pickle 反序列化 → root RCE =================
@APP.route("/api/deserialize", methods=["POST"])
def api_deserialize():
    try:
        data = request.form.get("data", "")
        obj = pickle.loads(base64.b64decode(data))
        return jsonify({"unpickled": str(obj)[:500]})
    except Exception as e:
        return jsonify({"error": str(e)})

# ================= 启动 =================
def main():
    db_init()
    print(f"* BioHazard CTF Lab 启动 (SECRET_KEY={'MYSQL' if MYSQL_HOST else 'SQLite'})")
    APP.run(host="0.0.0.0", port=int(os.environ.get("PORT", 80)), debug=False)

if __name__ == "__main__":
    main()