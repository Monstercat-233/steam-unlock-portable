# Steam 全自动入库工具（可移植版）

> **一句话结论（务必先读）：这套工具能自动把游戏"加进库并下载"，但能不能真正玩，取决于游戏本身的验证机制。最终只有「纯单机」和少数「Steam PVE 合作老游戏」能稳定玩。带自有账号、内核反作弊、第三方联机后端、或 Denuvo 未破解的游戏，工具再自动也救不回来。**

## 📦 版本导航（先看这里）

| 版本 | 目录 | 说明 | 状态 |
|---|---|---|---|
| **v2 入库中心 + v3 本体监控**（推荐） | [`入库中心_v2_v3/`](入库中心_v2_v3/) | 单 exe 4-tab GUI（入库/版本锁定/补丁/备份隔离），界面基于 **pywebview + WebView2**（4 套主题，深/浅即时切换），v3 新增启动自检监控已破解游戏本体更新。含 exe + 全部源码（Python 桥 + 单文件 HTML 前端）+ 测试 + 设计/验收文档 | ✅ 最新 |
| v1 可移植版 | [`src/`](src/) + `简单入库.exe` | 早期命令行 + 简单 GUI 版，保留作回退 | 旧版可用 |

- **v2 快速开始**：双击 `入库中心_v2_v3/入库中心.exe`（约 22MB，无需装 Python；界面用系统自带 WebView2，Win10/11 已内置），详见该目录 `使用说明.md`。
- **v2 界面**：顶栏（账号 chip / Steam 状态 chip / 主题下拉）+ 左侧 186px 导航 + 卡片式主面板 + 状态栏；主题 深色·Midnight（默认）/ 浅色·Daylight / 深色·Nord / 浅色·Solarized，选择记在 exe 同目录 `ui_prefs.json`。改外观只动 `入库中心_v2_v3/src/ui/index.html`。
- **v2 游戏封面卡片**：入库清单与搜索结果改为卡片墙，自动从 Steam CDN 拉取游戏横版封面（大图在上、游戏名在下），缓存在 exe 同目录 `covers\<AppID>.jpg`，断网复用缓存、无封面（如 DLC）显示占位图。
- **v3 启动自检**：打开 exe 后台只读比对已锁定游戏（如剑星）的 buildid/GID，版本变了弹窗提醒重锁重打补丁；只报不改、不常驻。详见 `入库中心_v2_v3/v3自动维护/使用说明.md`。
- v2/v3 全程不改 v1 产物，两者可共存；`baseline.json` / `audit.log` / `auto_adapt_cache.json` 为机器私有数据，已 `.gitignore` 排除。

---

配合 OpenSteamTool 使用的 Windows 工具，三块职责分离（以下为 v1 说明，v2/v3 见上方目录）：

| 部分 | 交付物 | 职责 |
|---|---|---|
| **A · 全自动入库** | `简单入库.exe`（GUI）/ `addgame_pro.py`（命令行） | 输入游戏名或 AppID → 自动联网取 depot key + 实时 manifest + DRM 判断 → 幂等写入 Steam 的 `mygames.lua` |
| **B · Denuvo 破解辅助** | `version_lock.py` + `apply_patch.py` + 两个拖拽 bat | 锁定历史版本 GID（下到能破解的旧版）→ 下完把破解补丁覆盖进游戏目录（带备份） |
| **C · 辅助脚本** | `denuvo_helper.py` / `addall.py` / `ost_toggle.bat` | Denuvo 指路、批量导入已装游戏、OST DLL 开关 |

> 家庭共享内存解锁启动器（原 B 部分）已移除：实测赢不了服务器踢人，且需要覆盖 Steam 注入，不可用。

---

## 一、能自动 / 不能自动

**能自动：**
- 按游戏名/AppID/商店链接解析 AppID（本地表 → Steam storesearch API）
- 从 steamcmd.net 拉该游戏全部 depot 列表 + 每个 depot 的实时 manifest GID
- 从 ManifestHub 全量 depot key 库（28.8 万条，随包分发，7 天可联网刷新）取每个 depot 的解密 key
- 从 Steam appdetails 读 Denuvo / VAC / 发行商，给出「能否下载 / 运行 / 联机」判断
- 生成带唯一标记的幂等 Lua 块：重复添加覆盖式写入，不留孤儿行
- 从破解包里自动提取历史 GID 并锁定（`version_lock.py --import`）
- 按目录结构把破解文件覆盖进游戏目录、覆盖前自动备份（`apply_patch.py`）

**不能自动（需人工，或无解）：**
- Denuvo 提票（需真拥有者账号 `extract_tickets`，票据 30 分钟有效）；破解补丁文件需自行下载
- 历史 GID 无权威 API（SteamDB 403、SteamManifestCache 讨论区超时），靠「破解库索引 + 用户上传破解包导入」
- 第三方联机后端（Photon 等）或自有账号+内核反作弊（EA / 微软 / 育碧）的联机

---

## 二、限制与已知问题（最重要，请完整阅读）

### 2.1 三关模型：入库 ≠ 能玩

任何游戏要能玩，必须连过三关；工具只稳定解决第一关。

| 关卡 | 通过条件 | 自动化程度 |
|---|---|---|
| **① 下载** | 该游戏存在公开的 depot key + manifest | ✅ 全自动（28.8万 key 库 + steamcmd.net 实时 manifest） |
| **② 运行** | 无 DRM，或有 Denuvo 但票据/补丁已就位 | ⚠️ 无 DRM 直接过；Denuvo 半自动（锁旧版+指路+填票据），提票和打补丁要人工 |
| **③ 联机** | Steamworks 票据有效，且无自有账号/内核反作弊 | ❌ 仅 Steam lobby 类可修；其余多数无解 |

典型能玩的（三关全通）：求生之路2、Hades/Hades II、空洞骑士、星露谷物语、Terraria 等**纯单机或 Steam PVE 合作老游戏**。

### 2.2 联机三分类（决定联机能不能修）

| 类型 | 判定方法 | 能否联机 |
|---|---|---|
| **A · Steam lobby / Steamworks 票据** | 用 Steam 原生大厅，无外部账号 | ✅ `启动Steam_联机.bat`（`-onlinefix`）可修。限制：同一时间只能一个此类联机游戏，走 480 大厅 |
| **B · 第三方联机后端**（Photon 等） | 游戏目录 `Managed\` 里有 `Photon*.dll`；报错 `customAuthenticationFailed`（0x7FFF-12） | ⚠️ 需游戏专用 mod（BepInEx 类，如 REPO Steam P2P），双方都要装 + 真人建房验证。曾尝试的 `OnlineFix.dll` 实测不稳（导致游戏进程起不来、影响其它游戏），**已移除，不建议再试** |
| **C · 自有账号 + 内核反作弊** | 启动弹 EA / 微软 Xbox Live / 育碧 Ubisoft Connect 登录；SteamDB 标 `EA_AntiCheat` / `Denuvo` + 反作弊 | ❌ **无解，联机必封号**。例：战地六（EA Javelin + 强制 Secure Boot）、COD、Apex、地平线6（Xbox Live）、育碧系列。`-onlinefix` 对这些完全无效 |

### 2.3 Denuvo（运行关）

- 判断依据：SteamDB 的 **3rd-Party DRM** 字段，或 Steam 商店页 "includes 3rd party DRM"。工具自带的 `drm` 字段常常为空（连黑神话都读到空），所以另有一份人工核实名单 `KNOWN_DENUVO`（剑星/影之刃零/黑神话）。
- 两条路线：
  1. **票据**：需真拥有者账号用 `extract_tickets.exe` 提取 AppTicket / ETicket，**30 分钟有效**，填进 `denuvo_helper.py --ticket`。本工具不含该提取程序。
  2. **补丁（推荐纯单机）**：找社区破解补丁替换游戏 exe（如剑星 Voices38 2026-05 经典破解，只换文件、无需关 Secure Boot / 装内核驱动）。**补丁只能打在对应的旧版本上**，所以必须先把游戏锁到破解版对应的历史 GID（见第三节 B 流程）。
- Denuvo 会跨校验 SteamID，票据必须与当前登录账号匹配，否则报错（error 54）。

### 2.4 家庭库显示 / ownership ticket 报错

- 若你的账号在**家庭组**里，假入库游戏会显示"来自家庭库"。
- 日志里大量 `failed to update ownership ticket (Access Denied)` —— 这是 OST 假入库的**固有噪音**，实测**与下载成败无关**（能下好的游戏也有这个错误），可以忽略。
- 有人试图用第三方 fork（huanyuejue）把游戏"脱离共享逻辑"来消除这个显示，但该 fork 会导致**假下载**（`0 updated, 0 moved, 0 deleted files`，`SizeOnDisk=0`，点开始游戏却没文件）——**已证伪，切勿使用**。只用随包的官方主版 `OpenSteamTool.dll`。

### 2.5 其它已知限制

- **VAC 封号风险**：玩 VAC / 竞技游戏前必须 `ost_toggle.bat` 菜单 [2] 移走三个 DLL，恢复纯净 Steam。DLL 常驻时进 VAC 官方服有封号风险。
- **manifest 上游**：`opensteamtool` 域名常被 Cloudflare 拦（403），配置模板已默认用 `wudrm`（实测可用）。
- **代理环境**：部分上游域名（raw.githubusercontent）经企业代理可能握手超时；key 库随包分发即为规避此问题。
- **两套注入不能共存**：SteamTools 与 OpenSteamTool 都劫持 `xinput1_4.dll`。SteamTools 会把锁定的历史 GID 覆盖回最新版，导致 `Missing decryption key`。**二选一**，本工具走纯 OST。

### 2.6 故障恢复（常见错误对照）

| 现象 | 原因 | 处理 |
|---|---|---|
| `Failed building depot dependency (Invalid content configuration)` / state `0x202`，下载不动 | `appinfo.vdf` 冻结在旧时刻，与内存 depot 依赖不一致（多次强杀/卸载/换注入后常见） | 退出 Steam → 备份并删除 `Steam安装目录\appcache\appinfo.vdf`、`appcache\appinfo\`、`opensteamtool\pattern\`、`opensteamtool\ipc\` → 冷启动 Steam 自动重建 |
| `Failed to initialize depot ..., manifest ... (Missing decryption key)` | 实际下载的 GID 与手里的 key/锁版不匹配（多因 SteamTools 覆盖回最新 GID，或 setManifestid 写成了字符串） | 确保纯 OST + `setManifestid(数字, "gid")` 数字写法 + 清 appinfo 冷启动 |
| 下载到的是最新版而非锁定版 / `setManifestid` 无效 | `setManifestid` 第一参数必须是**数字**，写成 `setManifestid("3489701",...)` 会被静默忽略 | `version_lock.py` 已用数字写法；手工改 lua 时也要数字 |
| 库/图标全没了，工具无反应 | 三件套 DLL 被删，OST 无法 hook | 把 `src\ost_dll\` 三个 DLL 复制回 Steam 目录；恢复 `opensteamtool\pattern\` 与 `ipc\` 缓存；重启 Steam |
| 点下载瞬间完成、0 文件、却显示可玩 | 用了会破坏依赖的第三方 fork（huanyuejue） | 换回主版 OpenSteamTool.dll（随包 `ost_dll` 内即主版），删掉假安装的 appmanifest 重新下 |
| 加游戏后 Steam 里看不到 | 未重启 Steam | 托盘右键完全退出（不是关窗口）再启动 |

---

## 三、安装（换一台新电脑）

### 前置
- Windows + Steam（能正常登录）
- Python 3.10+（仅源码运行/打包时需要；用现成 exe 不需要）
- 联网（key 库随包分发，联网仅用于刷新 key 库和拉实时 manifest）

### 步骤
1. 把整个目录放到任意位置（例：`D:\tools\steam-unlock\`）
2. **把 `config_template\opensteamtool.toml` 复制到 Steam 安装目录**（与 `steam.exe` 同级），文件名不变
3. **把 `src\ost_dll\` 里的三个 DLL**（`dwmapi.dll` / `xinput1_4.dll` / `OpenSteamTool.dll`）复制到 Steam 安装目录
   - 也可用 `ost_toggle.bat` 菜单 [1] 自动复制（需先完全退出 Steam）
4. 完全退出并重启 Steam 一次

Steam 目录无需手动指定：工具按以下顺序自动探测——环境变量 `STEAM_PATH` → 注册表 → 正在运行的 steam.exe → 常见安装目录。若自动探测失败，设一个环境变量 `STEAM_PATH=D:\你的Steam目录` 即可。

---

## 四、使用

### A · 入库（日常只用这个）

**GUI：** 双击 `简单入库.exe`
- 输入框填游戏名或 AppID → 点「添加入库」
- 下方列表是已入库的主游戏 AppID；可「移除选中」「刷新」
- 状态栏会显示能否下载、有无 Denuvo 等判断；无 key 时会红字警告"仅显示图标，下载不了"
- 「刷新Key库(7天)」手动更新全量 key 库

**命令行：** `python addgame_pro.py <游戏名/AppID>`
```
python addgame_pro.py 1145360                 # 单个
python addgame_pro.py "Hades" "Hollow Knight" # 多个
python addgame_pro.py --file games.txt        # 批量
python addgame_pro.py --list                  # 查看已入库
python addgame_pro.py --remove 550            # 移除
python addgame_pro.py --reload-keys           # 强制刷新 key 库
```

**批量导入本机已装游戏：** `python addall.py --list`（预览）/ `python addall.py --apply`（写入）

**入库后必须完全重启 Steam**（托盘右键退出，不是关窗口）才会显示新游戏。

### B · Denuvo 破解游戏完整流程（以剑星为例）

适用：有历史破解补丁的纯单机 Denuvo 游戏。核心是「锁到破解版对应的旧版本 → 下完覆盖补丁」。

1. **查妥当：** `python version_lock.py 3489700`（看破解库命中情况；未收录会提示缺历史 GID）
2. **锁定历史版本（下载前）：** 把破解包里的老版本 `.lua`（或整个破解包）拖到 `导入破解包.bat` 上 → 输入 AppID → 自动提取老 GID、数字写法写进 lua。
   - 已收录游戏可用命令行：`python version_lock.py 3489700 --lock 3489701=2747626496734343426 3596180=8344797041293440177 3596190=6588499701851943951`
   - 库里没有的游戏，先用 `--add-lib` 补一条，或直接拖拽导入。
3. **清缓存冷启动：** 完全退出 Steam → 删 `Steam安装目录\appcache\appinfo.vdf` → 重新启动 Steam。
4. **核对下载版本（关键）：** 打开 `Steam安装目录\logs\content_log.txt`，确认 `Downloading ... chunks for depot ... (2747626496734343426)` 里的 GID 是锁定值，不是实时值。错了就回头查 setManifestid 写法 / 是否混用了 SteamTools。
5. **下完覆盖补丁：** 把破解补丁包（zip 或文件夹）拖到 `导入补丁包.bat` 上 → 输入 AppID → 自动按目录结构覆盖进游戏目录，原文件备份在 `游戏目录\_patch_backup\`，可回滚。
6. **开玩：** 从 Steam 库启动（补丁自带 `steam_api64.dll` emu，不依赖 Steam 票据）。

> 两个 bat 的区别：**导入破解包.bat = 下之前用**（锁版本，传老 lua）；**导入补丁包.bat = 下完之后用**（覆盖破解文件）。都在 `src\` 目录下，拖文件图标上去即可，不用敲命令行。

### A · 联机启动 / 防封号开关
- `启动Steam_联机.bat`：带 `-onlinefix` 参数启动（**仅限** 2.2 表 A 类 Steamworks 大厅游戏）；前提完全退出 Steam 再运行。
- `ost_toggle.bat` 菜单 [2]：移走 Steam 目录里的三个 DLL，恢复纯净 Steam。玩 VAC / 竞技游戏前**务必先执行**。

### Denuvo 助手 / 破解库维护
```
python denuvo_helper.py 3489700                # 查这个 Denuvo 游戏该怎么过运行关
python denuvo_helper.py 3489700 --ticket HEX    # 填 AppTicket
python version_lock.py --list-lib              # 看破解库收录了哪些游戏
python version_lock.py --add-lib 4115450 "游戏名" "破解说明" "来源URL"   # 手动补库
```

---

## 五、从源码打包 exe（可选）

改了 `.py` 之后需重新打包才影响 exe：

```bat
REM 简单入库.exe
py -m PyInstaller --noconfirm --clean --onefile --windowed --name SimpleImport --distpath dist --workpath build --specpath . 简单入库.py
REM 把 dist\SimpleImport.exe 重命名为 简单入库.exe
```

注意：`steam_path.py` 必须和主脚本一起打包（PyInstaller 会自动跟踪 import）。key 库 `depotkeys_master.json` 需与 exe 同目录或其父目录，`get_deploy_dir()` 会自动定位。

---

## 六、目录结构

```
README.md                   本说明（含完整限制与故障恢复）
src/
  steam_path.py             统一路径探测（无硬编码，核心）
  auto_adapt.py             全自动适配核心（key/manifest/DRM）
  简单入库.py / addgame_pro.py / addall.py / denuvo_helper.py
  version_lock.py           Denuvo 历史版本锁定 + 破解库
  apply_patch.py            破解补丁覆盖（带备份）
  crack_library.json        破解库索引（已收录剑星 v1.4.1）
  _detect_steam.bat         bat 共用的 Steam 路径探测
  OST管理面板.bat / 启动Steam_联机.bat / ost_toggle.bat
  导入破解包.bat / 导入补丁包.bat   两个拖拽式破解工具
  ost_dll\                  三个注入 DLL（官方主版）
  depotkeys_master.json     ManifestHub 全量 key 库（16MB / 288381 条，随包分发）
  简单入库.exe              现成的 GUI 入库程序
config_template/
  opensteamtool.toml        配置模板（复制到 Steam 目录）
```

---

## 七、数据与隐私
- 不含任何账号、家庭组、appinfo 缓存等私有数据
- 16MB key 库随仓库分发（clone 即用，规避代理下载问题），运行时可联网刷新
- 运行时生成的缓存（`auto_adapt_cache.json`）已在 `.gitignore` 排除

## 八、外部信源
- depot key：github.com/SteamAutoCracks/ManifestHub
- manifest / depot 元数据：api.steamcmd.net
- DRM 判断：store.steampowered.com/api/appdetails
- 历史 GID / 破解版本：SteamManifestCache Discussions、社区破解包内的锁定版 lua
- OpenSteamTool：github.com/OpenSteam001/OpenSteamTool（官方主版）
