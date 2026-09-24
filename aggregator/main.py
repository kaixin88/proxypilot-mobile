#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ProxyPilot Mobile · 节点聚合入口

用法：
    python aggregator/main.py --out sub [--app-data app/data] [--no-probe]

产物：
    sub/nodes.json   手机 App 的数据源（含每条节点的分享链接）
    sub/clash.yaml   Clash / Clash Meta for Android 可直接导入的完整配置
    sub/sub.txt      base64 订阅（v2rayNG / NekoBox / sing-box 通用）
    sub/links.txt    明文分享链接，便于排查
"""

import argparse
import datetime
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import nodecore  # noqa: E402
import export  # noqa: E402


def write(path, text):
    d = os.path.dirname(path)
    if d:
        os.makedirs(d, exist_ok=True)
    if isinstance(text, bytes):
        with open(path, "wb") as f:
            f.write(text)
    else:
        with open(path, "w", encoding="utf-8") as f:
            f.write(text)
    print("  写出 %-24s %d 字节" % (path, len(text)))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="sub", help="产物输出目录")
    ap.add_argument("--app-data", default="", help="同步写一份 nodes.json 给 APK 离线用")
    ap.add_argument("--no-probe", action="store_true", help="跳过可用性探测")
    ap.add_argument("--timeout", type=int, default=2500, help="单节点探测超时(ms)")
    ap.add_argument("--limit", type=int, default=200, help="订阅里最多包含多少节点")
    args = ap.parse_args()

    print("== 抓取云端节点源 ==")
    nodes, stat = nodecore.sync_all(probe=not args.no_probe, timeout_ms=args.timeout)
    print("  %s" % json.dumps(stat, ensure_ascii=False))

    if not nodes:
        print("!! 本次没有拿到任何节点，保留上次结果")
        return 1

    # 只导出手机客户端真能连的
    usable = [n for n in nodes if export.exportable(n)]
    print("  可用且可导出：%d / %d" % (len(usable), len(nodes)))

    for n in usable:
        n["link"] = export.share_link(n)

    now = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    payload = {
        "updated": now,
        "count": len(usable),
        "stat": stat,
        "nodes": [
            {
                "id": n["id"],
                "name": n["name"],
                "protocol": n["protocol"],
                "server": n["server"],
                "port": n["port"],
                "latency": max(n.get("latency") or 0, 0),
                "source": n.get("source", ""),
                "link": n.get("link", ""),
            }
            for n in usable
        ],
    }

    print("== 生成产物 ==")
    write(os.path.join(args.out, "nodes.json"),
          json.dumps(payload, ensure_ascii=False, indent=1))
    write(os.path.join(args.out, "links.txt"), "\n".join(n.get("link", "") for n in usable))

    b64sub, links = export.build_base64_sub(usable, limit=args.limit)
    if b64sub:
        write(os.path.join(args.out, "sub.txt"), b64sub)
    yaml_text = export.build_clash_yaml(usable, limit=args.limit)
    if yaml_text:
        write(os.path.join(args.out, "clash.yaml"), yaml_text)

    if args.app_data:
        write(os.path.join(args.app_data, "nodes.json"),
              json.dumps(payload, ensure_ascii=False, separators=(",", ":")))

    print("完成：%d 个节点，更新于 %s" % (len(usable), now))
    return 0


if __name__ == "__main__":
    sys.exit(main())
