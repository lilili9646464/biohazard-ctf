#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
域控服务器 (仅内网可达: http://dc:389)
==================================================
剧情: 生化公司内网核心 —— 域控制器。
要拿到这里的 flag#4, 必须:
  1. 先通过 SSRF 从 backup 上偷到域控服务账号 (svc_dc / S3rv1c3_P@ss!_2026)
  2. 用该账号对 dc 进行 LDAP 身份认证

攻击链: SSRF -> backup -> dc_creds -> dc 认证 -> flag#4
"""
import os
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import urlparse, parse_qs

FLAG4 = "flag{D0m41n_C0ntr0ll3r_0wn3d}"

VALID_USER = "svc_dc"
VALID_PASS = "S3rv1c3_P@ss!_2026"

class Handler(BaseHTTPRequestHandler):
    def _reply(self, code, body):
        self.send_response(code)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Content-Length", str(len(body.encode())))
        self.end_headers()
        self.wfile.write(body.encode())
        self.close_connection = True

    def do_GET(self):
        u = urlparse(self.path)
        if u.path == "/":
            self._reply(200,
                        "Active Directory Domain Controller (模拟)\n"
                        "认证接口: /auth?user=xxx&pass=xxx\n")
            return
        if u.path == "/auth":
            q = parse_qs(u.query)
            user = (q.get("user") or [""])[0]
            pwd = (q.get("pass") or [""])[0]
            if user == VALID_USER and pwd == VALID_PASS:
                self._reply(200, f"LDAP 认证成功, 域管理员: {user}\n{FLAG4}")
            else:
                self._reply(403, "认证失败: 无效的服务账号凭据")
            return
        self._reply(404, "404 not found")

    def log_message(self, *a):
        pass

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 1389))
    print(f"* Domain controller :{port}")
    HTTPServer(("0.0.0.0", port), Handler).serve_forever()