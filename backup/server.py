#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
内网备份服务器 (仅内网可达: http://backup:8080)
==================================================
剧情: 生化公司的内部备份中心, 存放核心资料备份与运维凭据。
渗透者可通过 Web 应用上的 SSRF (/api/fetch?url=http://backup:8080/...) 访问。

这里藏着:
  - /archives/core_backup.txt   → flag#3 (核心数据备份)
  - /secrets/dc_creds.txt       → 域控服务账号口令 (横向移动的关键)
  - /backup.log                 → 备份日志
"""
import os
from http.server import BaseHTTPRequestHandler, HTTPServer

FLAG3 = "flag{B4ckup_0f_Th3_Und3ad}"

ROUTES = {
    "/": (
        "text/plain; charset=utf-8",
        "BioHazard Backup Center v3.2\n"
        "---------------------------------\n"
        "可用资源:\n"
        "  /backup.log          备份日志\n"
        "  /archives/          备份归档目录\n"
        "  /secrets/           运维凭据目录(危险!)\n"
        "  /archives/core_backup.txt   核心数据备份\n"
        "  /secrets/dc_creds.txt       域控服务账号\n",
    ),
    "/backup.log": (
        "text/plain; charset=utf-8",
        "2026-08-27 02:14  full backup OK  -> /archives/core_backup.txt\n"
        "2026-08-27 02:15  secret sync OK  -> /secrets/dc_creds.txt\n"
        "2026-08-27 02:16  user backup OK  (权限不足, 跳过)\n",
    ),
    "/archives/core_backup.txt": (
        "text/plain; charset=utf-8",
        f"[核心数据备份 20260827]\n{FLAG3}\n"
        "注: 生产库 config 在域控上有一份副本...\n",
    ),
    "/secrets/dc_creds.txt": (
        "text/plain; charset=utf-8",
        "[域控服务账号 - 请勿外泄]\n"
        "user: svc_dc\n"
        "pass: S3rv1c3_P@ss!_2026\n"
        "# 该账号仅允许在域控上进行 LDAP 身份认证访问\n",
    ),
}

class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        path = self.path.split("?")[0]
        if path in ROUTES:
            ctype, body = ROUTES[path]
            self.send_response(200)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body.encode())))
            self.end_headers()
            self.wfile.write(body.encode())
        else:
            self.send_response(404)
            self.send_header("Content-Type", "text/plain")
            self.end_headers()
            self.wfile.write(b"404 not found")
        self.close_connection = True

    def log_message(self, *a):
        pass

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    print(f"* Backup server :{port}")
    HTTPServer(("0.0.0.0", port), Handler).serve_forever()