#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
导出层：把归一化节点转成手机客户端能直接吃的东西。

  1. 分享链接  —— ss:// / ssr:// / vmess:// / vless:// / trojan:// /
                  hysteria:// / hysteria2://
  2. Clash 订阅 —— 完整 config.yaml（proxies + proxy-groups + rules）
  3. base64 订阅 —— 上面那些分享链接拼起来再整体 base64，v2rayNG 的标准格式

只输出「手机客户端真能连」的协议。桌面版踩过的坑这里继续遵守：
naiveproxy / juicity / mieru 在发行版内核里根本没编译进去，
写进 Clash 配置会让内核直接 fatal，所以一律不导出。
"""

import base64
import json
from urllib.parse import quote, urlencode

EXPORT_PROTOS = ("ss", "ssr", "vmess", "vless", "trojan", "hysteria", "hysteria2")


def b64(s):
    return base64.b64encode(s.encode("utf-8")).decode()


def b64url_strip(s):
    return base64.b64encode(s.encode("utf-8")).decode().rstrip("=")


def _name_frag(name):
    return "#" + quote(str(name or ""), safe="")


def _qs(params):
    parts = []
    for k, v in params.items():
        if v in (None, "", False):
            continue
        parts.append((k, str(v)))
    return ("?" + urlencode(parts)) if parts else ""


# ---------------------------------------------------------------- 分享链接

def link_ss(n):
    r = n["raw"]
    method = r.get("cipher") or r.get("method") or "aes-128-gcm"
    pwd = r.get("password") or ""
    userinfo = b64url_strip("%s:%s" % (method, pwd))
    plugin = ""
    if r.get("plugin"):
        plugin = "?plugin=" + quote("%s;%s" % (r.get("plugin"), r.get("plugin-opts", "")), safe="")
    return "ss://%s@%s:%d%s%s" % (userinfo, n["server"], n["port"], plugin, _name_frag(n["name"]))


def link_ssr(n):
    r = n["raw"]
    pwd = b64url_strip(r.get("password") or "")
    base = "%s:%d:%s:%s:%s:%s" % (n["server"], n["port"], r.get("protocol", "auth_aes128_md5"),
                                  r.get("cipher") or r.get("method") or "aes-128-cfb",
                                  r.get("obfs") or "plain", pwd)
    q = {}
    if r.get("obfs-param"):
        q["obfsparam"] = b64url_strip(r["obfs-param"])
    if r.get("protocol-param"):
        q["protoparam"] = b64url_strip(r["protocol-param"])
    q["remarks"] = b64url_strip(n["name"])
    return "ssr://" + b64url_strip(base + "/?" + urlencode(q))


def link_vmess(n):
    r = n["raw"]
    net = n.get("transport") or "tcp"
    if net == "h2":
        net = "http"
    obj = {
        "v": "2",
        "ps": n["name"],
        "add": n["server"],
        "port": str(n["port"]),
        "id": r.get("id") or r.get("uuid") or "",
        "aid": str(r.get("alterId") or r.get("alterid") or 0),
        "net": net,
        "type": r.get("type") or "none",
        "host": r.get("host") or r.get("sni") or "",
        "path": r.get("path") or "",
        "tls": "tls" if n.get("security") in ("tls", "reality") else "",
        "sni": r.get("sni") or "",
        "scy": r.get("security") if n.get("protocol") == "vmess" else "",
    }
    return "vmess://" + b64(json.dumps(obj, ensure_ascii=False, separators=(",", ":")))


def link_vless(n):
    r = n["raw"]
    enc = (r.get("encryption") or "none").strip()
    # 部分源会把一长串随机值塞进 encryption，写进链接会让客户端解析失败
    if enc.lower() != "none" and (len(enc) > 16 or " " in enc):
        enc = "none"
    q = {
        "encryption": enc,
        "security": n.get("security") or ("tls" if r.get("sni") else "none"),
        "type": n.get("transport") or "tcp",
        "sni": r.get("sni") or "",
        "flow": r.get("flow") or "",
        "fp": r.get("fingerprint") or "",
        "pbk": r.get("publicKey") or "",
        "sid": r.get("shortId") or "",
    }
    t = q["type"]
    if t in ("ws", "httpupgrade", "xhttp", "h2"):
        q["path"] = r.get("path") or "/"
        q["host"] = r.get("host") or r.get("sni") or ""
    elif t == "grpc":
        q["serviceName"] = r.get("serviceName") or ""
    if n.get("security") != "reality":
        q.pop("pbk", None)
        q.pop("sid", None)
    return "vless://%s@%s:%d%s%s" % (r.get("id") or r.get("uuid") or "", n["server"],
                                     n["port"], _qs(q), _name_frag(n["name"]))


def link_trojan(n):
    r = n["raw"]
    q = {
        "security": n.get("security") or "tls",
        "sni": r.get("sni") or "",
        "type": n.get("transport") or "tcp",
        "alpn": r.get("alpn") or "",
        "fp": r.get("fingerprint") or "",
    }
    t = q["type"]
    if t in ("ws", "httpupgrade", "xhttp"):
        q["path"] = r.get("path") or "/"
        q["host"] = r.get("host") or ""
    elif t == "grpc":
        q["serviceName"] = r.get("serviceName") or ""
    if not q["alpn"]:
        q.pop("alpn")
    return "trojan://%s@%s:%d%s%s" % (quote(r.get("password") or "", safe=""), n["server"],
                                      n["port"], _qs(q), _name_frag(n["name"]))


def link_hysteria2(n):
    r = n["raw"]
    pwd = r.get("password") or r.get("auth_str") or r.get("auth-str") or r.get("auth") or ""
    q = {
        "sni": r.get("sni") or "",
        "insecure": "1" if str(r.get("insecure", "")).lower() in ("1", "true") else "",
        "obfs": r.get("obfs") or "",
        "obfs-password": r.get("obfs-password") or "",
    }
    return "hysteria2://%s@%s:%d%s%s" % (quote(pwd, safe=""), n["server"], n["port"],
                                         _qs(q), _name_frag(n["name"]))


def link_hysteria(n):
    """hysteria v1：v2rayNG / sing-box 用的是 hysteria://host:port?auth=..&peer=.."""
    r = n["raw"]
    q = {
        "peer": r.get("sni") or "",
        "auth": _hysteria_auth(r),
        "upmbps": str(r.get("up_mbps") or r.get("up") or "").replace("Mbps", ""),
        "downmbps": str(r.get("down_mbps") or r.get("down") or "").replace("Mbps", ""),
        "insecure": "1" if str(r.get("insecure", "")).lower() in ("1", "true") else "",
        "protocol": "udp",
    }
    return "hysteria://%s:%d%s%s" % (n["server"], n["port"], _qs(q), _name_frag(n["name"]))


LINK_BUILDERS = {
    "ss": link_ss,
    "ssr": link_ssr,
    "vmess": link_vmess,
    "vless": link_vless,
    "trojan": link_trojan,
    "hysteria2": link_hysteria2,
    "hysteria": link_hysteria,
}


def share_link(n):
    fn = LINK_BUILDERS.get((n.get("protocol") or "").lower())
    if not fn:
        return ""
    try:
        return fn(n)
    except Exception:
        return ""


def exportable(n):
    """能否导出：协议被手机客户端支持，且关键凭据齐全。"""
    p = (n.get("protocol") or "").lower()
    if p not in EXPORT_PROTOS:
        return False
    r = n.get("raw") or {}
    if p in ("ss", "ssr"):
        return bool(r.get("password") and (r.get("cipher") or r.get("method")))
    if p in ("vmess", "vless"):
        return bool(r.get("id") or r.get("uuid"))
    if p == "trojan":
        return bool(r.get("password"))
    if p == "hysteria2":
        return bool(r.get("password") or r.get("auth_str") or r.get("auth"))
    if p == "hysteria":
        return bool(_hysteria_auth(r))
    return False


def _hysteria_auth(r):
    """hysteria v1 的口令在不同源里字段名不一致：auth / auth_str / auth-str。"""
    for k in ("auth", "auth_str", "auth-str", "password"):
        if r.get(k):
            return str(r[k])
    return ""


# ---------------------------------------------------------------- Clash 配置

def clash_proxy(n):
    """归一化节点 -> clash proxy 字典。"""
    r = n.get("raw") or {}
    p = (n.get("protocol") or "").lower()
    # clash 的 server 字段不带方括号（IPv6 直接写地址）
    server = n["server"]
    if server.startswith("[") and server.endswith("]"):
        server = server[1:-1]
    d = {"name": n["name"], "type": p, "server": server, "port": n["port"]}

    if p == "ss":
        d.update({"cipher": r.get("cipher") or r.get("method") or "aes-128-gcm",
                  "password": r.get("password") or "", "udp": True})
        if r.get("plugin"):
            d["plugin"] = r["plugin"]
            if r.get("plugin-opts"):
                d["plugin-opts"] = _infer_plugin_opts(r)
    elif p == "ssr":
        d.update({"cipher": r.get("cipher") or r.get("method") or "aes-128-cfb",
                  "password": r.get("password") or "",
                  "protocol": r.get("protocol") or "auth_aes128_md5",
                  "obfs": r.get("obfs") or "plain"})
    elif p == "vmess":
        d.update({"uuid": r.get("id") or r.get("uuid") or "",
                  "alterId": int(r.get("alterId") or 0),
                  "cipher": r.get("security") or "auto", "udp": True})
        _apply_transport(d, n, r)
    elif p == "vless":
        d.update({"uuid": r.get("id") or r.get("uuid") or "", "udp": True})
        if r.get("flow"):
            d["flow"] = r["flow"]
        _apply_transport(d, n, r)
    elif p == "trojan":
        d.update({"password": r.get("password") or "", "udp": True})
        _apply_transport(d, n, r)
    elif p == "hysteria":
        # mihomo 要求 up/down 带单位（"100 Mbps"），裸数字会导致解析失败
        d.update({"auth-str": _hysteria_auth(r),
                  "up": _bw(r.get("up_mbps") or r.get("up")),
                  "down": _bw(r.get("down_mbps") or r.get("down")),
                  "protocol": "udp"})
        if r.get("sni"):
            d["sni"] = r["sni"]
        d["skip-cert-verify"] = True
        if r.get("alpn"):
            d["alpn"] = [x.strip() for x in str(r["alpn"]).split(",") if x.strip()]
    elif p == "hysteria2":
        d.update({"password": r.get("password") or r.get("auth_str") or r.get("auth") or ""})
        if r.get("sni"):
            d["sni"] = r["sni"]
        d["skip-cert-verify"] = True
        if r.get("obfs"):
            d["obfs"] = r["obfs"]
            if r.get("obfs-password"):
                d["obfs-password"] = r["obfs-password"]
    else:
        return None
    return {k: v for k, v in d.items() if v not in (None, "", [])}


def _bw(v):
    """带宽值补单位：20 -> '20 Mbps'。"""
    s = str(v or "10").strip()
    if not s:
        return "10 Mbps"
    if any(s.lower().endswith(u) for u in ("mbps", "kbps", "gbps", "mb/s", "kb/s")):
        return s
    return s + " Mbps"


def _infer_plugin_opts(r):
    opts = {}
    for kv in str(r.get("plugin-opts", "")).split(";"):
        if "=" in kv:
            k, v = kv.split("=", 1)
            opts[k.strip()] = v.strip()
    return opts


def _apply_transport(d, n, r):
    net = (n.get("transport") or "tcp").lower()
    sec = (n.get("security") or "").lower()
    if sec == "reality":
        d["tls"] = True            # reality 必须配 tls 服务端信息
        d["servername"] = r.get("sni") or ""
        d["reality-opts"] = {"public-key": r.get("publicKey") or ""}
        if r.get("shortId"):
            d["reality-opts"]["short-id"] = r["shortId"]
        if r.get("fingerprint"):
            d["client-fingerprint"] = r["fingerprint"]
    elif sec == "tls":
        d["tls"] = True
        if r.get("sni"):
            d["servername"] = r["sni"]
        if r.get("alpn"):
            d["alpn"] = [x.strip() for x in str(r["alpn"]).split(",") if x.strip()]
        d.setdefault("skip-cert-verify", True)
    if net in ("ws", "httpupgrade"):
        d["network"] = "ws"
        opts = {"path": r.get("path") or "/"}
        if r.get("host"):
            opts["headers"] = {"Host": r["host"]}
        d["ws-opts"] = opts
    elif net == "xhttp":
        d["network"] = "xhttp"
        opts = {"path": r.get("path") or "/"}
        if r.get("host"):
            opts["headers"] = {"Host": r["host"]}
        if r.get("mode"):
            opts["mode"] = r["mode"]
        d["xhttp-opts"] = opts
    elif net == "grpc":
        d["network"] = "grpc"
        if r.get("serviceName"):
            d["grpc-opts"] = {"grpc-service-name": r["serviceName"]}
    elif net == "h2":
        d["network"] = "h2"
        if r.get("path"):
            d["h2-opts"] = {"path": r["path"]}
        if r.get("host"):
            d.setdefault("h2-opts", {})["host"] = [r["host"]]


def yaml_scalar(v):
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, (int, float)):
        return str(v)
    s = str(v)
    if s == "":
        return '""'
    needs = (s[0] in "&*?|-<>=!%@`\"'{[" or ":" in s or "#" in s or "\n" in s
             or s.lower() in ("yes", "no", "true", "false", "null", "~", "on", "off"))
    if needs:
        return '"' + s.replace("\\", "\\\\").replace('"', '\\"') + '"'
    return s


def dump_yaml_block(obj, indent):
    """把 dict / list 转成 YAML 文本块（不支持嵌套 dict 之外的复杂结构）。"""
    pad = " " * indent
    lines = []
    if isinstance(obj, list):
        for item in obj:
            if isinstance(item, dict):
                block = dump_yaml_block(item, indent + 2).split("\n")
                lines.append("%s- %s" % (pad, block[0].lstrip()))
                lines.extend(block[1:])
            else:
                lines.append("%s- %s" % (pad, yaml_scalar(item)))
        return "\n".join(lines)
    for k, v in obj.items():
        if isinstance(v, dict):
            lines.append("%s%s:" % (pad, k))
            lines.append(dump_yaml_block(v, indent + 2))
        elif isinstance(v, list):
            if v and all(isinstance(x, (str, int, float, bool)) for x in v):
                lines.append("%s%s:" % (pad, k))
                for x in v:
                    lines.append("%s  - %s" % (pad, yaml_scalar(x)))
            else:
                lines.append("%s%s:" % (pad, k))
                lines.append(dump_yaml_block(v, indent + 2))
        else:
            lines.append("%s%s: %s" % (pad, k, yaml_scalar(v)))
    return "\n".join(lines)


CLASH_HEADER = """# ProxyPilot Mobile —— 自动生成，请勿手工编辑
# 由 GitHub Actions 定时从云端节点源聚合、去重、测速后生成
mixed-port: 7890
allow-lan: false
mode: rule
log-level: warning
geodata-mode: true
ipv6: false
external-controller: 127.0.0.1:9090

dns:
  enable: true
  enhanced-mode: fake-ip
  fake-ip-range: 198.18.0.1/16
  nameserver:
    - https://1.1.1.1/dns-query
    - https://8.8.8.8/dns-query
  fallback:
    - https://dns.google/dns-query
  fallback-filter:
    geoip: true
    ipcidr:
      - 240.0.0.0/4

proxies:
"""

CLASH_TAIL = """
proxy-groups:
  - name: 🚀 自动选择
    type: url-test
    proxies: ALL_NODES
    url: https://www.gstatic.com/generate_204
    interval: 300
    tolerance: 50
  - name: 🎯 手动选择
    type: select
    proxies:
      - 🚀 自动选择
      - ALL_NODES
  - name: 🐟 漏网之鱼
    type: select
    proxies:
      - 🚀 自动选择
      - 🎯 手动选择
      - DIRECT

rules:
  - MATCH,🐟 漏网之鱼
"""


def build_clash_yaml(nodes, limit=200):
    proxies = []
    names = []
    for n in nodes:
        if not exportable(n):
            continue
        d = clash_proxy(n)
        if not d:
            continue
        # 名称去重（clash 不允许同名 proxy）
        name = d["name"]
        if name in names:
            name = "%s #%d" % (name, names.count(name) + 1)
            d["name"] = name
        names.append(name)
        proxies.append(d)
        if len(proxies) >= limit:
            break
    if not proxies:
        return ""
    body = dump_yaml_block(proxies, 2)
    # 展开代理组里的 ALL_NODES 占位符（列表形式）
    all_block = "\n".join("      - " + yaml_scalar(p["name"]) for p in proxies)
    tail = CLASH_TAIL.replace(
        """    proxies:
      - 🚀 自动选择
      - ALL_NODES""",
        "    proxies:\n      - 🚀 自动选择\n" + all_block,
    ).replace("    proxies: ALL_NODES", "    proxies:\n" + all_block)
    return CLASH_HEADER + body + tail


# v2rayNG 基于 xray-core，只认下面这些；hysteria v1 它解析不了，
# 混在订阅里只会冒出一片「不支持」的红色节点，所以单独出一份干净的订阅。
V2RAYNG_PROTOS = ("ss", "ssr", "vmess", "vless", "trojan", "hysteria2")


def build_base64_sub(nodes, limit=200, protos=None):
    links = []
    for n in nodes:
        if not exportable(n):
            continue
        if protos and (n.get("protocol") or "").lower() not in protos:
            continue
        lk = share_link(n)
        if lk:
            links.append(lk)
        if len(links) >= limit:
            break
    if not links:
        return "", []
    return b64("\n".join(links)), links
