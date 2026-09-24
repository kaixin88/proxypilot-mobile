#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
节点聚合核心：抓取 -> 解析 -> 去重 -> 探测。

逻辑完整复刻自 Windows 端 ProxyPilot 的 Go 实现：
  sources.go   —— 26 个云端节点源（主源 + 2 个镜像）
  parser.go    —— 手写的 clash.yaml / xray / sing-box / hysteria / juicity /
                  naiveproxy / mieru 解析（不引入任何第三方依赖）
  manager.go   —— 跨源合并去重、保底保留旧节点、协议感知探测
  node.go      —— 以「协议+服务器+端口」做 SHA1 指纹

只依赖 Python 标准库，因此可以直接在 GitHub Actions 上跑，无需安装任何包。

与桌面版的差异（移动端需要真正的可导入配置，所以做了两点增强）：
  1. 解析 clash.yaml 时保留**全部原始字段**（桌面版只挑了几个），
     否则生成分享链接 / 订阅时会丢掉 uuid、password 等关键信息。
  2. 输出层新增「分享链接 / Clash 订阅 / base64 订阅」三种产物。
"""

import hashlib
import json
import socket
import ssl
import time
import urllib.request
import urllib.error
from concurrent.futures import ThreadPoolExecutor

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) ProxyPilot/1.0"

# ---------------------------------------------------------------- 节点源

# 远端目录名与本地内核名不一致（本地 clash.meta\ -> 远端 clash.meta2\），
# 必须以远端实际路径为准，这条踩过坑，别改。
def default_sources():
    out = []
    for i in range(1, 7):
        out.append({"kind": "clash.meta", "dir": "clash.meta2", "index": i, "file": "config.yaml"})
    for i in range(1, 5):
        out.append({"kind": "xray", "dir": "xray", "index": i, "file": "config.json"})
    for i in range(1, 3):
        out.append({"kind": "singbox", "dir": "singbox", "index": i, "file": "config.json"})
    for i in range(1, 5):
        out.append({"kind": "hysteria2", "dir": "hysteria2", "index": i, "file": "config.json"})
        out.append({"kind": "hysteria", "dir": "hysteria", "index": i, "file": "config.json"})
    for i in range(1, 3):
        out.append({"kind": "juicity", "dir": "juicity", "index": i, "file": "config.json"})
        out.append({"kind": "naiveproxy", "dir": "naiveproxy", "index": i, "file": "config.json"})
        out.append({"kind": "mieru", "dir": "mieru", "index": i, "file": "config.json"})
    return out


def source_label(s):
    return "%s-ip%d" % (s["kind"], s["index"])


def source_mirrors(s):
    """主源在前，备用镜像在后，依次尝试。"""
    name = "%s/%d/%s" % (s["dir"], s["index"], s["file"])
    return [
        "https://gitlab.com/free9999/ipupdate/-/raw/master/backup/img/1/2/ipp/" + name,
        "https://www.67867867.xyz/Alvin9999/PAC/refs/heads/master/backup/img/1/2/ipp/" + name,
        "https://raw.githubusercontent.com/Alvin9999-newpac/PAC/master/backup/img/1/2/ipp/" + name,
    ]


# ---------------------------------------------------------------- 抓取

def looks_like_config(txt, fname):
    """粗筛响应内容，避免把 404 页面当成配置。必须检查全文——
    Xray 的 outbounds 段可能出现在很靠后的位置（前面是大段 dns 配置）。"""
    if "\n" not in txt and len(txt) < 40:
        return False
    if txt.strip().startswith("<"):     # HTML 错误页
        return False
    if fname == "config.yaml":
        return "proxies:" in txt
    return "{" in txt and "}" in txt


def fetch_source(s, timeout=20):
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    for url in source_mirrors(s):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=timeout, context=ctx) as resp:
                if resp.status != 200:
                    continue
                body = resp.read(4 << 20).decode("utf-8", "replace")
            if len(body) < 20:
                continue
            if not looks_like_config(body, s["file"]):
                continue
            return body, True
        except Exception:
            continue
    return "", False


# ---------------------------------------------------------------- Node

class Node(dict):
    """用 dict 承载，方便直接序列化成 JSON。"""

    @property
    def id(self):
        return self.get("id", "")


def finalize(n):
    protocol = (n.get("protocol") or "").lower()
    server = n.get("server") or ""
    port = int(n.get("port") or 0)
    if not server or not port or not protocol:
        return None
    n["protocol"] = protocol
    n["server"] = server
    n["port"] = port
    n["name"] = (n.get("name") or "").strip() or "%s://%s:%d" % (protocol, server, port)
    n.setdefault("transport", "")
    n.setdefault("security", "")
    n.setdefault("raw", {})
    key = "|".join([protocol, server.lower(), str(port)])
    n["id"] = hashlib.sha1(key.encode("utf-8")).hexdigest()[:16]
    n.setdefault("latency", 0)
    n.setdefault("ok", False)
    return n


# ---------------------------------------------------------------- 解析：clash.yaml

def parse_clash_yaml(src, label):
    """轻量手写解析：proxies 是顶层键，每项以 '  - name: xxx' 开始，
    字段缩进 4 空格。避免为了一个文件引入 yaml 依赖。"""
    nodes = []
    in_proxies = False
    cur = None

    def flush():
        nonlocal cur
        if cur is None:
            return
        n = clash_map_to_node(cur, label)
        if n:
            nodes.append(n)
        cur = None

    for raw_line in src.replace("\r\n", "\n").split("\n"):
        line = raw_line.rstrip(" \t")
        trimmed = line.lstrip(" ")
        if not trimmed or trimmed.startswith("#"):
            continue
        if not line.startswith(" "):                 # 顶层键
            flush()
            in_proxies = (trimmed == "proxies:")
            continue
        if not in_proxies:
            continue
        indent = len(line) - len(trimmed)
        if indent == 2 and trimmed.startswith("- "):  # 新节点项
            flush()
            cur = {}
            trimmed = trimmed[2:]
        if cur is None:
            continue
        idx = trimmed.find(":")
        if idx <= 0:
            continue                                  # 续行列表项（如 "  - h3"）
        k = trimmed[:idx].strip()
        v = trimmed[idx + 1:].strip().strip("\"'")
        if k == "alpn" and v == "":
            continue
        cur.setdefault(k, v)
    flush()
    return nodes


def clash_map_to_node(m, label):
    server = m.get("server", "")
    try:
        port = int(str(m.get("port", "0")).strip())
    except ValueError:
        port = 0
    if not server or not port:
        return None
    ptype = (m.get("type") or "").lower()
    if not ptype:
        return None
    proto = ptype
    if proto == "hy2":
        proto = "hysteria2"
    elif proto == "shadowsocks":
        proto = "ss"

    n = Node(
        name=m.get("name", ""),
        protocol=proto,
        server=server,
        port=port,
        source=label,
        transport="udp" if proto in ("hysteria", "hysteria2") else "tcp",
        security="tls" if proto in ("hysteria", "hysteria2") else m.get("security", ""),
        # 保留全部原始字段：生成分享链接 / Clash 订阅时要用 uuid、password 等
        raw=dict(m),
    )
    return finalize(n)


# ---------------------------------------------------------------- 解析：xray / sing-box / 其他 json

def _s(v):
    if v is None:
        return ""
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, float) and v == int(v):
        return str(int(v))
    if isinstance(v, (int, float)):
        return str(v)
    if isinstance(v, str):
        return v
    if isinstance(v, list):
        return ",".join(_s(x) for x in v)
    return ""


def _i(v):
    try:
        if isinstance(v, str):
            return int(v.strip())
        return int(v)
    except Exception:
        return 0


def parse_xray_json(src, label):
    try:
        cfg = json.loads(src)
    except Exception:
        return []
    nodes = []
    for ob in cfg.get("outbounds") or []:
        if not isinstance(ob, dict):
            continue
        proto = _s(ob.get("protocol")).lower()
        if not proto or proto in ("freedom", "blackhole", "dns"):
            continue
        settings = ob.get("settings") or {}
        stream = ob.get("streamSettings") or {}
        n = Node(name=_s(ob.get("tag")), protocol=proto, source=label, raw={})
        raw = {}

        if proto in ("vless", "vmess"):
            vnext = settings.get("vnext") or []
            if not vnext:
                continue
            first = vnext[0]
            n["server"] = _s(first.get("address"))
            n["port"] = _i(first.get("port"))
            users = first.get("users") or []
            if users:
                u = users[0]
                raw["id"] = _s(u.get("id"))
                if proto == "vless":
                    raw["flow"] = _s(u.get("flow"))
                    raw["encryption"] = _s(u.get("encryption"))
                else:
                    raw["security"] = _s(u.get("security"))
                    raw["alterId"] = _s(u.get("alterId"))
        elif proto in ("trojan", "shadowsocks"):
            servers = settings.get("servers") or []
            if not servers:
                continue
            first = servers[0]
            n["server"] = _s(first.get("address"))
            n["port"] = _i(first.get("port"))
            if proto == "trojan":
                raw["password"] = _s(first.get("password"))
            else:
                raw["method"] = _s(first.get("method"))
                raw["password"] = _s(first.get("password"))
                proto = "ss"
                n["protocol"] = "ss"
        else:
            continue

        if stream:
            n["transport"] = _s(stream.get("network"))
            n["security"] = _s(stream.get("security"))
            tls = stream.get("tlsSettings") or {}
            raw["sni"] = _s(tls.get("serverName"))
            raw["alpn"] = _s(tls.get("alpn"))
            if stream.get("realitySettings"):
                rs = stream["realitySettings"]
                raw["sni"] = _s(rs.get("serverName"))
                raw["publicKey"] = _s(rs.get("publicKey"))
                raw["shortId"] = _s(rs.get("shortId"))
                raw["fingerprint"] = _s(rs.get("fingerprint"))
                n["security"] = "reality"
            for key, cfg_key in (("xhttpSettings", "xhttp"), ("wsSettings", "ws"), ("grpcSettings", "grpc")):
                seg = stream.get(key) or {}
                if seg:
                    if cfg_key == "grpc":
                        raw["serviceName"] = _s(seg.get("serviceName"))
                    else:
                        raw["path"] = _s(seg.get("path"))
                        raw["host"] = _s(seg.get("host")) or _s(seg.get("headers", {}).get("Host"))
                        if cfg_key == "xhttp":
                            raw["mode"] = _s(seg.get("mode"))
        n["raw"] = {k: v for k, v in raw.items() if v not in ("", None)}
        node = finalize(n)
        if node:
            nodes.append(node)
    return nodes


def parse_singbox_json(src, label):
    try:
        cfg = json.loads(src)
    except Exception:
        return []
    nodes = []
    skip = ("direct", "block", "dns", "selector", "urltest")
    for ob in cfg.get("outbounds") or []:
        if not isinstance(ob, dict):
            continue
        proto = _s(ob.get("type")).lower()
        if not proto or proto in skip:
            continue
        server = _s(ob.get("server"))
        port = _i(ob.get("server_port"))
        if not server or not port:
            continue
        raw = {}
        tls = ob.get("tls") or {}
        sec = ""
        if tls.get("enabled"):
            sec = "tls"
            raw["sni"] = _s(tls.get("server_name"))
            raw["insecure"] = _s(tls.get("insecure"))
        raw["auth_str"] = _s(ob.get("auth_str")) or _s(ob.get("password"))
        raw["up_mbps"] = _s(ob.get("up_mbps"))
        raw["down_mbps"] = _s(ob.get("down_mbps"))
        raw["uuid"] = _s(ob.get("uuid"))
        raw["password"] = _s(ob.get("password"))
        raw["method"] = _s(ob.get("method"))
        n = Node(
            name=_s(ob.get("tag")), protocol=proto, server=server, port=port,
            source=label, transport="udp" if proto in ("hysteria", "hysteria2") else "tcp",
            security=sec, raw={k: v for k, v in raw.items() if v},
        )
        node = finalize(n)
        if node:
            nodes.append(node)
    return nodes


def split_host_port(s):
    s = (s or "").strip()
    if not s:
        return "", 0
    if s.startswith("["):
        idx = s.rfind("]:")
        if idx > 0:
            return s[:idx + 1], _i(s[idx + 2:])
        return s, 0
    idx = s.rfind(":")
    if idx > 0:
        p = _i(s[idx + 1:])
        if p > 0:
            return s[:idx], p
    return s, 0


def parse_hysteria_json(src, label, is_v2):
    try:
        cfg = json.loads(src)
    except Exception:
        return []
    if not isinstance(cfg, dict):
        return []
    server = _s(cfg.get("server"))
    if not server:
        return []
    host, port = split_host_port(server)
    if not host or not port:
        return []
    proto = "hysteria2" if is_v2 else "hysteria"
    raw = {}
    tls = cfg.get("tls") or {}
    raw["sni"] = _s(tls.get("sni"))
    raw["insecure"] = _s(tls.get("insecure"))
    if is_v2:
        raw["password"] = _s(cfg.get("auth")) or _s(cfg.get("password")) or _s(cfg.get("auth_str"))
        raw["obfs"] = _s(cfg.get("obfs"))
        raw["obfs-password"] = _s(cfg.get("obfs-password"))
    else:
        raw["auth"] = _s(cfg.get("auth")) or _s(cfg.get("auth_str")) or _s(cfg.get("password"))
        raw["up_mbps"] = _s(cfg.get("up_mbps")) or _s(cfg.get("up"))
        raw["down_mbps"] = _s(cfg.get("down_mbps")) or _s(cfg.get("down"))
        raw["protocol"] = "udp"
    n = Node(
        name="%s %s" % (label, proto), protocol=proto, server=host, port=port,
        source=label, transport="udp", security="tls",
        raw={k: v for k, v in raw.items() if v},
    )
    node = finalize(n)
    return [node] if node else []


def parse_juicity_json(src, label):
    try:
        cfg = json.loads(src)
    except Exception:
        return []
    host, port = split_host_port(_s(cfg.get("server")))
    if not host or not port:
        return []
    n = Node(name=label + " juicity", protocol="juicity", server=host, port=port, source=label,
             transport="quic", security="tls",
             raw={"uuid": _s(cfg.get("uuid")), "password": _s(cfg.get("password")),
                  "sni": _s(cfg.get("sni"))})
    node = finalize(n)
    return [node] if node else []


def parse_naive_json(src, label):
    try:
        cfg = json.loads(src)
    except Exception:
        return []
    proxy = _s(cfg.get("proxy"))
    if not proxy:
        return []
    rest = proxy.split("://", 1)[-1]
    userinfo = ""
    if "@" in rest:
        at = rest.rfind("@")
        userinfo = rest[:at]
        rest = rest[at + 1:]
    host, port = split_host_port(rest)
    if not host or not port:
        return []
    raw = {"scheme": "https"}
    if userinfo:
        parts = userinfo.split(":", 1)
        raw["username"] = parts[0]
        if len(parts) > 1:
            raw["password"] = parts[1]
    n = Node(name=label + " naiveproxy", protocol="naiveproxy", server=host, port=port,
             source=label, transport="tcp", security="tls", raw=raw)
    node = finalize(n)
    return [node] if node else []


def parse_mieru_json(src, label):
    try:
        cfg = json.loads(src)
    except Exception:
        return []
    out = []
    for p in cfg.get("profiles") or []:
        user = p.get("user") or {}
        for srv in p.get("servers") or []:
            host = _s(srv.get("ipAddress")) or _s(srv.get("domainName"))
            if not host:
                continue
            for pb in srv.get("portBindings") or []:
                port = _i(pb.get("port"))
                if not port:
                    continue
                n = Node(name=label + " mieru", protocol="mieru", server=host, port=port,
                         source=label, transport=_s(pb.get("protocol")).lower() or "tcp",
                         security="tls",
                         raw={"username": _s(user.get("name")), "password": _s(user.get("password"))})
                node = finalize(n)
                if node:
                    out.append(node)
    return out


def parse_by_kind(kind, content, label):
    if kind == "clash.meta":
        return parse_clash_yaml(content, label)
    if kind == "xray":
        return parse_xray_json(content, label)
    if kind == "singbox":
        return parse_singbox_json(content, label)
    if kind == "hysteria2":
        return parse_hysteria_json(content, label, True)
    if kind == "hysteria":
        return parse_hysteria_json(content, label, False)
    if kind == "juicity":
        return parse_juicity_json(content, label)
    if kind == "naiveproxy":
        return parse_naive_json(content, label)
    if kind == "mieru":
        return parse_mieru_json(content, label)
    return []


# ---------------------------------------------------------------- 探测

UDP_PROTOS = ("hysteria", "hysteria2", "juicity", "shadowquic", "quic", "tuic")


def is_udp_proto(n):
    p = (n.get("protocol") or "").lower()
    if p in UDP_PROTOS:
        return True
    return "udp" in (n.get("transport") or "").lower()


def probe_tcp(n, timeout_ms):
    addr = (n["server"].strip("[]"), n["port"])
    start = time.time()
    try:
        s = socket.create_connection(addr, timeout=timeout_ms / 1000.0)
        lat = int((time.time() - start) * 1000)
        s.close()
        return max(lat, 1), True
    except Exception:
        return -1, False


def probe_udp(n, timeout_ms):
    """QUIC 服务端收到非法握手包通常不回应，也不返回 ICMP 不可达。
    因此「没有被明确拒绝」即视为可达，避免把大量可用节点误判。"""
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.settimeout(timeout_ms / 1000.0)
        payload = bytes([0xC0, 0, 0, 0, 1, 8, 0, 0, 0, 0, 0, 0])
        start = time.time()
        sock.sendto(payload, (n["server"].strip("[]"), n["port"]))
        try:
            data, _ = sock.recvfrom(1500)
            lat = int((time.time() - start) * 1000)
            sock.close()
            return max(lat, 1), True
        except socket.timeout:
            sock.close()
            return -1, True          # 静默 = 可达（QUIC 常见）
        except Exception as e:
            sock.close()
            msg = str(e).lower()
            refused = ("refused" in msg or "unreachable" in msg or "reset" in msg
                       or "forcibly closed" in msg)
            return -1, not refused
    except Exception:
        return -1, False


def probe_node(n, timeout_ms):
    if is_udp_proto(n):
        return probe_udp(n, timeout_ms)
    return probe_tcp(n, timeout_ms)


def probe_all(nodes, timeout_ms=2500, workers=48):
    def work(i):
        ms, ok = probe_node(nodes[i], timeout_ms)
        nodes[i]["latency"] = ms
        nodes[i]["ok"] = ok

    with ThreadPoolExecutor(max_workers=workers) as ex:
        list(ex.map(work, range(len(nodes))))


# ---------------------------------------------------------------- 合并

def merge_nodes(fresh, old):
    """以指纹去重；新抓到的优先，旧节点仅作保底补入（防止某次抓取失败清空列表）。"""
    by_id = {}
    order = []

    def add(n):
        nid = n["id"]
        if nid not in by_id:
            order.append(nid)
        by_id[nid] = n

    for n in fresh:
        add(n)
    for n in old:
        if n["id"] not in by_id:
            add(n)
    return [by_id[i] for i in order]


def sort_nodes(nodes):
    def rank(n):
        lat = n.get("latency") or 0
        return 1 << 30 if lat <= 0 else lat

    nodes.sort(key=lambda n: (not n.get("ok"), rank(n), n.get("name") or ""))
    return nodes


def sync_all(probe=True, timeout_ms=2500, old=None, verbose=True):
    sources = default_sources()
    fetched = []
    parsed_nodes = []

    def work(s):
        body, ok = fetch_source(s)
        return (s, body, ok)

    with ThreadPoolExecutor(max_workers=len(sources)) as ex:
        for s, body, ok in ex.map(work, sources):
            if ok and body:
                nodes = parse_by_kind(s["kind"], body, source_label(s))
                fetched.append(source_label(s))
                parsed_nodes.extend(nodes)
                if verbose:
                    print("  %-22s -> %d 个节点" % (source_label(s), len(nodes)))
            elif verbose:
                print("  %-22s -> 抓取失败" % source_label(s))

    parsed = len(parsed_nodes)
    result = {"totalSources": len(sources), "fetchedSources": len(fetched), "parsed": parsed}

    merged = merge_nodes(parsed_nodes, old or [])
    result["merged"] = len(merged)

    if probe:
        probe_all(merged, timeout_ms)

    # 桌面版铁律：UDP 类探测不到延迟也保留（标记待验证），
    # 但移动端只给用户「能一键导入就能连」的节点，所以统一按 ok 过滤。
    final = [n for n in merged if not probe or n.get("ok")]
    result["removed"] = len(merged) - len(final)
    sort_nodes(final)

    if probe:
        result["alive"] = sum(1 for n in final if n.get("ok"))
    else:
        result["alive"] = len(final)
    return final, result
