# 入库中心 v2/v3 · 前端/UI 美化交接说明（HANDOFF）

> 给接手的 agent / Cursor：**先读完本文件再动手**。项目上下文已固化在这里，不需要向用户复述背景。

## 0. 一句话定位

这是 **Windows 桌面工具（Python + pywebview/WebView2）**。UI 由两部分组成：`src/main_app.py`（Python 侧，约 594 行，负责 `js_api` 桥与后端编排）+ `src/ui/index.html`（单文件 HTML/CSS/JS 前端，约 999 行，负责全部外观）。其余 8 个 .py 是已稳定的后端模块，改 UI 只动这两个文件。

> **当前已选路线：B（pywebview）**。历史上先做过路线 A（ttkbootstrap 2.2.7），成果保留在 `D:\AI_Workplace\agents\Extra\.work\main_app_ttk_v2.py`（源码）与 `.work\入库中心_ttk.exe`（41920615 B）作为回退。本轮最终交付是 pywebview 版：`入库中心.exe` 22423960 B。

## 1. 现状与文件地图

| 类别 | 文件 | 说明 |
|---|---|---|
| **UI · Python 侧（可大改）** | `src/main_app.py` | pywebview `js_api` 桥：`Bridge` 暴露 boot/search_games/add_game/apply_lock/scan_patch/backup_now 等 20 个方法，`main()` 建窗 + `webview.start()` |
| **UI · 前端（可大改）** | `src/ui/index.html` | 单文件前端：顶栏 + 186px 侧导航 + 4 panel + 底部状态栏；4 套主题（dark/light/nord/solar）用 CSS 变量切换 |
| 图标 | `src/app.ico` | 由 `main_app.py` 内嵌 Base64 PNG 生成，spec 用 `icon=` 嵌入 exe |
| 后端（只调用，勿改逻辑） | `src/paths.py` | 路径探测：`find_steam_dir()/lua_path()/writable_dir()/resource_dir()`，**禁止硬编码盘符** |
| 后端 | `src/auto_adapt.py` | 联网取 depot key + 实时 manifest + DRM 判断，写 `mygames.lua` |
| 后端 | `src/version_lock.py` | 锁定历史 GID（下到可破解旧版）；`setManifestid` 第一参数必须是**数字** |
| 后端 | `src/apply_patch.py` | 补丁覆盖（带备份） |
| 后端 | `src/backup.py` | 快照/回滚/体检/审计 |
| 后端 | `src/game_index.py` | 游戏名搜索（本地 names.json + Steam storesearch） |
| 后端 | `src/update_guard.py` | v3 启动自检：只读比对已破解游戏的 buildid/GID，只报不改 |
| 后端 | `src/denuvo_helper.py` | Denuvo 票据/补丁指路 |
| 数据 | `depotkeys_master.json` | 16MB / 288381 条 depot key，随包分发，勿改格式 |
| 数据 | `crack_library.json` / `names.json` | 破解库（剑星 3489700 verified=true）/ 游戏名缓存 |
| 打包 | `RukuCenter.spec` / `build.ps1` | PyInstaller onefile → `入库中心.exe`（约 22MB，pywebview 版；ttk 版为 41MB） |
| 文档 | `使用说明.md` / `验收记录.md` / `v3自动维护/` | 现有行为与验收基线 |

**4 个 tab 当前职责**：入库（搜索/入库/移除/打开目录 + 三态状态栏）、版本锁定（破解库列表/应用锁定/导入破解包）、补丁（appid + 路径/dry-run 预览/确认覆盖）、备份与隔离（账号下拉/快照/回滚/体检/审计）。

## 2. UI 路线（已落地：B）

### A · 保留 tkinter + ttkbootstrap（已完成，作为回退）
- 实现：`ttkbootstrap 2.2.7`，`one-light/one-dark` 双主题 + 14 套可选；中性灰 `Card.TLabelframe`；自定义 `Treeview.Heading`/`TNotebook.Tab` 映射；顶栏 `Header.TFrame` + 语义胶囊；内嵌 64×64 PNG 图标。
- 成果：964 行 `main_app.py`，exe 41920615 B，`ui_prefs.json` 记忆主题。
- 备份位置：`D:\AI_Workplace\agents\Extra\.work\main_app_ttk_v2.py`、`.work\入库中心_ttk.exe`。
- **上限**：原生控件，无 Web 动效/响应式。

### B · pywebview + WebView2（当前交付）
- 实现：`pywebview 6.2.1` + 系统自带 WebView2（本机 157.0.4341.60，Win10/11 自带，**exe 不打包浏览器内核**）。
- 前端：`src/ui/index.html` 单文件，CSS 变量令牌 + `html[data-theme]` 四套配色；顶栏/侧栏/卡片/斑马纹表格/Toast/模态确认框/按钮内嵌 spinner。
- 通信：`create_window(html=..., js_api=Bridge())` + `http_server=False`；js_api 方法由 pywebview 在**独立 daemon 线程**执行，不冻结 UI。
- **必守陷阱**：`Bridge` 上任何公开属性都会被 pywebview 的 `inject_pywebview` 递归扫描，窗口句柄等必须用下划线前缀（`self._window`），否则 `AccessibilityObject` 无限递归导致白屏 + 窗口未响应。
- 成果：`main_app.py` 594 行 + `index.html` 999 行，exe 22423960 B（比 ttk 版小 19.5MB），启动 1.06s（ttk 版 1.51s）。

## 3. 硬约束（必须遵守）

1. **不改后端 8 个 .py 的函数行为**，只在 `main_app.py` 调用它们。
2. **不动 v1 目录**（`简单入库.exe` / 旧 `src/`），它是回退基线。
3. 所有路径走 `paths.py`，禁止写死 `D:\STEAM` 之类。
4. 改完必须能重新 PyInstaller 打包 + 冒烟：onefile 启动后**按窗口标题找子进程**（`Start-Process` 返回的父进程无标题）。
5. `baseline.json` / `audit.log` / `auto_adapt_cache.json` 是机器私有数据，`.gitignore` 已排除，不入库。
6. 中文路径：PowerShell 直接跑含中文路径的 `.ps1` 会读坏，打包用内联命令并设 `PYTHONUTF8=1`。

## 4. 验收标准

- 4 个 tab 功能全部保留；exe 可启动、无 stderr、窗口标题 `入库中心 · OpenSteamTool 全自动 v2` 存在、响应正常。
- 后端 8 个 .py 与数据 json 哈希不变；v1 七文件哈希不变。
- `使用说明.md` 同步更新界面说明。

### 冒烟要点（pywebview 版与 tkinter 版不同）

- 窗口类名是 `WindowsForms10.Window.8.app.0.*_ad1`，**不是** `TkTopLevel`；按标题枚举时务必连类名一起过滤，否则会误匹配机器上残留的旧 tkinter 版进程。
- 冒烟前先 `taskkill` 掉残留的 `入库中心.exe`，否则拿到的是旧窗口。
- `subprocess.communicate()` 对 onefile + windowed 会挂住，用 `Popen` + 轮询窗口再 `kill`。
- `SendMessageTimeoutW(hwnd, WM_NULL)` 必须在 kill 之前采样，否则窗口已销毁。
- 截图用 `PrintWindow(hwnd, hdc, 2)`（`PW_RENDERFULLCONTENT`）+ `GetDIBits`；WebView2 窗口要等到真实尺寸 > 300px 再抓，否则空图。
- 切 tab/主题后建议用 `ImageChops.difference(...).getbbox()` 像素比对确认真的切了（点击坐标可能未命中）。

## 5. 本地验证命令（PowerShell）

```powershell
$env:PYTHONUTF8 = "1"
# 源码态跑测试
& "C:\Python314\python.exe" -m pytest "..\全自动入库_v2\tests" -q
# 重新打包（在 全自动入库_v2 目录，用 .spec）
& "C:\Python314\python.exe" -m PyInstaller RukuCenter.spec --noconfirm
```

## 6. 新对话启动提示词（直接复制）

```
先读 ./入库中心_v2_v3/HANDOFF.md（含文件地图/约束/验收），不要问我背景。
任务：[改 UI：src/main_app.py（Bridge）+ src/ui/index.html]。
只改这两个文件（+必要的 .spec 与前端资源），不动后端 8 个 .py 和 v1 目录，路径全走 paths.py。
改完按 HANDOFF §4 自检（pytest / PyInstaller 打包 / 按窗口标题+类名冒烟 / 截图）并给出改动清单。
```

前端外观改动通常只动 `src/ui/index.html`，不动 Python；只有新增/改变能力才改 `Bridge`。这样新 agent 一轮就能开工，无需复述整个项目历史。

## 7. 仓库与推送

- 私有仓库 `https://github.com/Monstercat-233/steam-unlock-portable`，本目录对应远端 `入库中心_v2_v3/`。
- git over HTTPS 在本网络被阻断（直连重置 / 代理 503）；此前用 GitHub REST API 推送成功。若需再次推送，优先用 API 或先排查网络。
- 本机 git 已配 `http.postBuffer=524288000`、`http.version=HTTP/1.1`、`http.lowSpeedLimit=0`、`http.lowSpeedTime=999999`；`git fetch` 偶发 `early EOF`，重试即可成功。
- 首次 `fetch` 后远端 commit 已被 GitHub 重算 hash（同树不同 commit），对齐用 `git update-ref refs/heads/master <sha>` + `git reset --mixed <sha>`（`reset --hard` 会被工作区安全网拦截）。
- `*.spec` 在 `.gitignore` 里，但 `入库中心_v2_v3/RukuCenter.spec` 需要跟踪 → 用 `git add -f`。
