#!/usr/bin/env python3
"""通过 GitHub Contents API 推送文件（适用于空仓库，无需 git 协议）。带重试。"""
import base64
import json
import os
import sys
import time
import urllib.parse
import urllib.request
import urllib.error

TOKEN = os.environ.get("GH_TOKEN", "")
REPO = os.environ.get("GH_REPO", "kaixin88/proxypilot")
SRC = os.environ.get("SRC_DIR", ".")
BRANCH = os.environ.get("GH_BRANCH", "main")
API = "https://api.github.com"

SKIP_DIRS = {".git", "dist", "data", "data_test", "bin", "__pycache__"}
SKIP_EXT = {".exe", ".dat", ".db", ".test", ".zip", ".log"}

RETRIES = 5


def req(method, path, data=None, retries=RETRIES):
    body = json.dumps(data).encode() if data is not None else None
    last_err = None
    for attempt in range(1, retries + 1):
        r = urllib.request.Request(API + path, data=body, method=method)
        r.add_header("Authorization", "token " + TOKEN)
        r.add_header("Accept", "application/vnd.github+json")
        r.add_header("Content-Type", "application/json")
        r.add_header("User-Agent", "ProxyPilot-Push")
        try:
            with urllib.request.urlopen(r, timeout=120) as resp:
                raw = resp.read()
                return json.loads(raw) if raw else {}
        except urllib.error.HTTPError as e:
            detail = e.read().decode(errors="replace")[:400]
            # 404/409 等业务错误不重试
            if e.code in (404, 409, 422):
                raise RuntimeError(f"{method} {path} -> {e.code}: {detail}")
            last_err = RuntimeError(f"{method} {path} -> {e.code}: {detail}")
        except Exception as e:  # 网络抖动，重试
            last_err = RuntimeError(f"{method} {path} -> {type(e).__name__}: {e}")
        wait = min(2 ** attempt, 20)
        print(f"    ... 第 {attempt} 次失败({last_err})，{wait}s 后重试")
        time.sleep(wait)
    raise last_err


def collect(root):
    out = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
        for fn in filenames:
            if os.path.splitext(fn)[1].lower() in SKIP_EXT:
                continue
            full = os.path.join(dirpath, fn)
            rel = os.path.relpath(full, root).replace("\\", "/")
            if rel.startswith(".git/"):
                continue
            out.append((rel, full))
    return sorted(out)


def put_file(rel, full, msg):
    with open(full, "rb") as f:
        content = f.read()
    payload = {
        "message": msg,
        "content": base64.b64encode(content).decode(),
        "branch": BRANCH,
    }
    try:
        existing = req("GET", f"/repos/{REPO}/contents/{urllib.parse.quote(rel)}?ref={BRANCH}")
        if isinstance(existing, dict) and existing.get("sha"):
            payload["sha"] = existing["sha"]
    except RuntimeError:
        pass
    res = req("PUT", f"/repos/{REPO}/contents/{urllib.parse.quote(rel)}", payload)
    return res.get("commit", {}).get("sha", "")


def ensure_branch():
    """确认分支存在；只有当仓库确实为空（无 commit）时才初始化。"""
    try:
        req("GET", f"/repos/{REPO}/git/ref/heads/{BRANCH}")
        return True  # 分支已存在
    except RuntimeError as e:
        msg = str(e)
        # 只有在明确"分支不存在"(404/409)时才初始化；网络错误直接报错退出
        if "-> 404" not in msg and "-> 409" not in msg:
            print(f"无法确认分支状态: {e}")
            return False
    print("分支不存在，创建初始提交 ...")
    boot = "# ProxyPilot\n\n正在初始化仓库 ...\n"
    req("PUT", f"/repos/{REPO}/contents/README.md", {
        "message": "chore: init repository",
        "content": base64.b64encode(boot.encode()).decode(),
        "branch": BRANCH,
    }, retries=2)
    return True


def main():
    if not TOKEN:
        print("缺少 GH_TOKEN")
        return 1

    if not ensure_branch():
        return 1

    files = collect(SRC)
    print(f"待推送文件: {len(files)} 个")
    last_sha = ""
    failed = []
    for rel, full in files:
        try:
            sha = put_file(rel, full, f"update {rel}")
            last_sha = sha or last_sha
            print(f"  ✓ {rel}")
        except RuntimeError as e:
            print(f"  ✗ {rel}: {e}")
            failed.append(rel)
    print(f"最新提交: {last_sha[:8] if last_sha else 'n/a'}")
    if failed:
        print(f"失败 {len(failed)} 个: {failed}")
        return 1
    print("PUSH_OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
