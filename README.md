# ProxyPilot Mobile · 手机可用版

手机上的「节点面板」：自动拉取、合并、测速 26 个云端节点源，
在手机浏览器（**PWA，可加到主屏幕**）或安装的 APK 里一键导入
**Clash / Clash Meta / v2rayNG / NekoBox / sing-box**。

> 这只是**节点管理与一键导入**——实际代理要靠手机上已装的客户端。
> 走的是 `clash://` / `v2rayng://` / `sing-box://` 这些自定义 scheme。

## 链接

| 用途 | 地址 |
|---|---|
| 🌐 手机网页（PWA，加到主屏幕） | https://kaixin88.github.io/proxypilot-mobile/ |
| 📦 APK 下载（直接装） | https://github.com/kaixin88/proxypilot-mobile/releases/download/apk-latest/app-debug.apk |
| 🗂 仓库 | https://github.com/kaixin88/proxypilot-mobile |
| 📋 Clash / Meta 订阅 | https://cdn.jsdelivr.net/gh/kaixin88/proxypilot-mobile@main/sub/clash.yaml |
| 📋 v2rayNG 订阅（已剔除 hysteria） | https://cdn.jsdelivr.net/gh/kaixin88/proxypilot-mobile@main/sub/v2rayng.txt |
| 📋 NekoBox / sing-box 订阅（全协议） | https://cdn.jsdelivr.net/gh/kaixin88/proxypilot-mobile@main/sub/sub.txt |

> 国内访问订阅若卡顿，把链接里的 `cdn.jsdelivr.net` 换成
> `raw.githubusercontent.com` 或 `kaixin88.github.io` 即可，三条线路 App 里都有切换按钮。

---

## 只用 v2rayNG，不装本 App？完全可以

订阅链接本身就是最终产物，本 App 只是「看节点 + 帮你点一下导入」的壳。
直接用 v2rayNG 的步骤：

1. 装好 v2rayNG，打开 → 左上角菜单 → **订阅设置**
2. 右上角 **＋** → 备注随便填（比如 `ProxyPilot`）
3. **地址(URL)** 填上面表格里的 `v2rayng.txt` 那条
4. 右上角 ✓ 保存 → 回到首页 → 右上角 ⋮ → **更新订阅**
5. 节点出来后点一个 → 底部 **V 按钮** 连接

> ⚠️ **一定要用 `v2rayng.txt` 那条，不要用 `sub.txt`。**
> 云端这批节点大多是 `hysteria`（v1），v2rayNG 基于 xray-core **不支持 hysteria**，
> 用通用订阅会看到一片「不支持」的红节点。`v2rayng.txt` 已经替你筛掉了。
> 想连 hysteria 节点请用 **Clash Meta for Android**（喂 `clash.yaml`）或
> **NekoBox / sing-box**（喂 `sub.txt`）。

想让它长期自动更新：订阅设置里打开 **自动更新**（默认每 12 小时），
或每次手动点「更新订阅」——服务端每 3 小时重跑一次聚合。

## 怎么用

### 方式 A：浏览器（最快）
打开 https://kaixin88.github.io/proxypilot-mobile/ → Safari/Chrome → 分享 → 加到主屏幕。

### 方式 B：装 APK
[下载](https://github.com/kaixin88/proxypilot-mobile/releases/tag/apk-latest) →
允许未知来源 → 安装。APK 是个轻量 WebView 壳，与 PWA 是同一份前端代码，
自带一份最新节点快照，离线也能查看。

### 操作
1. 等「节点数」刷新出来（默认每 3 小时 GitHub Actions 跑一次）
2. 点节点列表里的任意一行 → 切换为「当前节点」
3. 点底部「连接」→ 选客户端（v2rayNG / Clash / NekoBox）→ 自动跳转到对应客户端导入订阅
4. 在那个客户端里点连接 → 完成

如果某个订阅线路在国内打不开，点订阅卡片里的「切换」换 jsDelivr / Pages / raw 三个线路之一。

---

## 工作原理（给好奇的人看）

跟桌面端 ProxyPilot 是同一套逻辑：

| 步骤 | 桌面端 | 移动端 |
|---|---|---|
| 抓取 26 个云端节点源 | Go 本地进程 | **GitHub Actions 定时跑 Python** |
| 解析 8 种内核配置 | 手写 parser.go | 手写 parser（`aggregator/nodecore.py`） |
| 跨源合并去重 | manager.go | `nodecore.merge_nodes` |
| TCP / UDP 协议感知探测 | manager.go | 同上 |
| 客户端内核 | Mihomo (Clash.Meta) | **手机已装的 v2rayNG / Clash / NekoBox** |
| 一键开启 | 系统代理 | **跳转客户端 + 导入订阅** |

每个云端源默认有 3 个镜像（GitLab / GitHub / 自建），
任一可用即成功，避免单点失效。

---

## 目录结构

```
proxypilot-mobile/
├── aggregator/
│   ├── nodecore.py     抓取 / 解析 / 合并 / 探测（核心逻辑，零依赖）
│   ├── export.py       分享链接 / Clash 订阅 / base64 订阅
│   └── main.py         入口
├── app/                前端单页 App（PWA 源）
│   ├── index.html      所有 UI 与逻辑
│   ├── manifest.json   PWA 配置
│   ├── sw.js           Service Worker
│   ├── icon-192.png    PWA 图标
│   └── data/nodes.json 由 Actions 生成，APK 里用这份做兜底
├── android/             APK WebView 壳（Java，不依赖本地构建）
│   └── app/src/main/...
├── tools/
│   ├── make_icons.py   纯标准库生成图标（不装 Pillow）
│   └── push_contents_api.py  工具：备用 API 推送脚本
├── .github/workflows/
│   ├── update-nodes.yml   每 3 小时跑聚合 + 发 Pages
│   └── build-apk.yml      编译 Android APK + 发 Release
└── sub/                生成的订阅产物（不入 git）
```

---

## 自己跑一遍

```bash
# 只用 Python 标准库（不需要 pip install 任何东西）
python3 aggregator/main.py --out sub --app-data app/data
```

可选：装上 pyyaml 后会顺便校验 Clash 订阅能被解析：
```bash
pip install pyyaml
```

---

## 铁律（沿用桌面版）

- 🚫 **绝不在 Clash 配置里写 naiveproxy / juicity / shadowtls**——发行版内核没编译，
  会直接 fatal（铁律 #3）。
- 🚫 UDP 探测「超时」不等于不可达，QUIC 服务端常常不回非法握手包，
  所以默认按可达处理（铁律 #4）。
- 🚫 订阅里出现的所有节点**必须是手机客户端能直接吃的协议**：
  ss / ssr / vmess / vless / trojan / hysteria / hysteria2。