# 入库中心 v2/v3 · 前端/UI 美化交接说明（HANDOFF）

> 给接手的 agent / Cursor：**先读完本文件再动手**。项目上下文已固化在这里，不需要向用户复述背景。

## 0. 一句话定位

这是 **Windows 桌面工具（Python + tkinter）**，不是网页项目。UI 是**单个文件** `src/main_app.py`（约 490 行）；其余 8 个 .py 是已稳定的后端模块，本次任务只动 UI 表现层。

## 1. 现状与文件地图

| 类别 | 文件 | 说明 |
|---|---|---|
| **UI（本次唯一可大改）** | `src/main_app.py` | tkinter `ttk.Notebook` 4 个 tab 的构建与事件 |
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
| 打包 | `RukuCenter.spec` / `build.ps1` | PyInstaller onefile → `入库中心.exe`（约 21MB） |
| 文档 | `使用说明.md` / `验收记录.md` / `v3自动维护/` | 现有行为与验收基线 |

**4 个 tab 当前职责**：入库（搜索/入库/移除/打开目录 + 三态状态栏）、版本锁定（破解库列表/应用锁定/导入破解包）、补丁（appid + 路径/dry-run 预览/确认覆盖）、备份与隔离（账号下拉/快照/回滚/体检/审计）。

## 2. UI 美化两条路线（先选一条再动手）

### A · 保留 tkinter（低风险，推荐先做）
- `ttkbootstrap` 或 `sv-ttk` 换现代主题；统一字体/Padding/配色；Card 式 `LabelFrame`；状态栏颜色语义；图标用内嵌 PNG/emoji。
- 保留原 PyInstaller 打包链，`.spec` 加 `--add-data` 带主题库。
- **上限**：仍是桌面原生控件，没有 Web 动效/响应式布局。适合"看着不丑、好用"。

### B · 换 Web 前端（高上限，工作量大）
- Tauri 或 Electron + React/Vue；Python 后端改成本地 HTTP/RPC 服务，或保留 exe 后端 + `pywebview` 承载。
- Cursor 的 Web 前端能力可全力发挥；但要重写整个 GUI 层 + 新打包链 + 进程通信。
- 适合"想要真正现代界面"，代价是数倍工作量与回归面。

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
任务：[选 A：保留 tkinter 做主题与布局美化 / 选 B：改 Web 前端]。
只改 src/main_app.py（+必要的 .spec 与主题依赖），不动后端 8 个 .py 和 v1 目录。
改完按 HANDOFF §4 自检并给出改动清单。
```

把 `[选 A / 选 B]` 替换成实际选择即可。这样新 agent 一轮就能开工，无需复述整个项目历史。

## 7. 仓库与推送

- 私有仓库 `https://github.com/Monstercat-233/steam-unlock-portable`，本目录对应远端 `入库中心_v2_v3/`。
- git over HTTPS 在本网络被阻断（直连重置 / 代理 503）；此前用 GitHub REST API 推送成功。若需再次推送，优先用 API 或先排查网络。
