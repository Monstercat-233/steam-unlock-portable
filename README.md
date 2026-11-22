# Steam 全自动入库 + 家庭共享解锁工具（可移植版）

> **一句话结论（务必先读）：这套工具能自动把游戏"加进库并下载"，但能不能真正玩，取决于游戏本身的验证机制。最终只有「纯单机」和少数「Steam PVE 合作老游戏」能稳定玩。带自有账号、内核反作弊、第三方联机后端、或 Denuvo 未破解的游戏，工具再自动也救不回来。**

一套配合 OpenSteamTool 使用的 Windows 工具，两大部分职责分离：

| 部分 | 交付物 | 职责 |
|---|---|---|
| **A · 全自动入库** | `简单入库.exe`（GUI）/ `addgame_pro.py`（命令行） | 输入游戏名或 AppID → 自动联网取 depot key + 实时 manifest + DRM 判断 → 幂等写入 Steam 的 `mygames.lua` |
| **B · 家庭共享解锁启动器** | `SteamFamilyUnlock.exe` | 用 schtasks 跳板启动 Steam → 内存 patch（`CUser::UpdateFamilyRunningApps` NOP）→ 守护重 patch。DLL 常驻。 |

> 入库/下载层（A）和内存 patch 层（B）是两个不同层，互不重复。日常只用得到 A；只有在需要内存解锁时才用 B。

---

## 一、能自动 / 不能自动

**能自动：**
- 按游戏名/AppID/商店链接解析 AppID（本地表 → Steam storesearch API）
- 从 steamcmd.net 拉该游戏全部 depot 列表 + 每个 depot 的实时 manifest GID
- 从 ManifestHub 全量 depot key 库（28.8 万条，随包分发，7 天可联网刷新）取每个 depot 的解密 key
- 从 Steam appdetails 读 Denuvo / VAC / 发行商，给出「能否下载 / 运行 / 联机」判断
- 生成带唯一标记的幂等 Lua 块：重复添加覆盖式写入，不留孤儿行

**不能自动（需人工，或无解）：**
- Denuvo 提票（需真拥有者账号 `extract_tickets`，票据 30 分钟有效）或打绕过补丁
- 第三方联机后端（Photon 等）或自有账号+内核反作弊（EA / 微软 / 育碧）的联机

---

## 二、限制与已知问题（最重要，请完整阅读）

### 2.1 三关模型：入库 ≠ 能玩

任何游戏要能玩，必须连过三关；工具只稳定解决第一关。

| 关卡 | 通过条件 | 自动化程度 |
|---|---|---|
| **① 下载** | 该游戏存在公开的 depot key + manifest | ✅ 全自动（28.8万 key 库 + steamcmd.net 实时 manifest） |
| **② 运行** | 无 DRM，或有 Denuvo 但票据/补丁已就位 | ⚠️ 无 DRM 直接过；Denuvo 只能半自动（指路/填票据），提票和打补丁要人工 |
| **③ 联机** | Steamworks 票据有效，且无自有账号/内核反作弊 | ❌ 仅 Steam lobby 类可修；其余多数无解 |

典型能玩的（三关全通）：求生之路2、Hades/Hades II、空洞骑士、星露谷物语、Terraria 等**纯单机或 Steam PVE 合作老游戏**。

### 2.2 联机三分类（决定联机能不能修）

| 类型 | 判定方法 | 能否联机 |
|---|---|---|
| **A · Steam lobby / Steamworks 票据** | 用 Steam 原生大厅，无外部账号 | ✅ `启动Steam_联机.bat`（`-onlinefix`）可修。限制：同一时间只能一个此类联机游戏，走 480 大厅 |
| **B · 第三方联机后端**（Photon 等） | 游戏目录 `Managed\` 里有 `Photon*.dll`；报错 `customAuthenticationFailed`（0x7FFF-12） | ⚠️ 需游戏专用 mod（BepInEx 类，如 REPO Steam P2P），双方都要装 + 真人建房验证。随附的 `OnlineFix.dll` 实测在本机不稳（会导致 REPO 进程起不来、影响其它游戏），**已移除，不建议再试** |
| **C · 自有账号 + 内核反作弊** | 启动弹 EA / 微软 Xbox Live / 育碧 Ubisoft Connect 登录；SteamDB 标 `EA_AntiCheat` / `Denuvo` + 反作弊 | ❌ **无解，联机必封号**。例：战地六（EA Javelin + 强制 Secure Boot）、COD、Apex、地平线6（Xbox Live）、育碧系列。`-onlinefix` 对这些完全无效 |

### 2.3 Denuvo（运行关）

- 判断依据：SteamDB 的 **3rd-Party DRM** 字段，或 Steam 商店页 "includes 3rd party DRM"。
- 已知带 Denuvo 的例子：剑星（3489700）、黑神话悟空（2358720）、影之刃零（4115450）、生化危机系列、刺客信条、霍格沃茨之遗、彩虹六号、FF7重生、P5R 等。
- 两条路线：
  1. **票据**：需真拥有者账号用 `extract_tickets.exe` 提取 AppTicket / ETicket，**30 分钟有效**，填进 `denuvo_helper.py --ticket`。本机无此工具。
  2. **补丁**：找社区破解补丁替换游戏 exe（如剑星 Voices38 2026-05 经典破解，只换文件、无需关 Secure Boot / 装内核驱动）。纯单机游戏首选这条。
- `denuvo_helper.py` 只能做到**检测 + 指路 + 填票据槽位**，提票和打补丁必须人工。
- 注意：Denuvo 会跨校验 SteamID，票据必须与当前登录账号匹配，否则报错（error 54）。

### 2.4 家庭共享鉴权冲突

- 若你的账号在**家庭组**里，假入库游戏会显示"来自家庭库"。
- 日志里大量 `failed to update ownership ticket (Access Denied)` —— 这是 OST 假入库的**固有噪音**，实测**与下载成败无关**（能下好的游戏也有这个错误），可以忽略。
- 有人试图用第三方 fork（huanyuejue）把游戏"脱离共享逻辑"来消除这个显示，但该 fork 会导致**假下载**（`0 updated, 0 moved, 0 deleted files`，`SizeOnDisk=0`，点开始游戏却没文件）——**已证伪，切勿使用**。
- 家庭共享本身规则：一份副本同一时间只能 1 人玩；借来的副本联机游戏会被拒；免费游戏/DLC 不共享。

### 2.5 其它已知限制

- **VAC 封号风险**：玩 VAC / 竞技游戏前必须 `ost_toggle.bat` 菜单 [2] 移走三个 DLL，恢复纯净 Steam。DLL 常驻时进 VAC 官方服有封号风险。
- **DRM 字段不可靠**：Steam `appdetails` 的 `drm_notice` 常常为空（连黑神话都读到空），工具标"无 DRM"**不等于真没 Denuvo**。判断请以 SteamDB 为准。
- **数据时效性**：ManifestHub key 库社区维护，新游戏 key 可能滞后；manifest GID 会随官方更新而过期的（如黑神话 2358721 旧 GID 已 STALE），工具每次联网拉实时 GID 规避。
- **manifest 上游**：`opensteamtool` 域名常被 Cloudflare 拦（403），配置模板已默认用 `wudrm`（实测可用）。
- **代理环境**：部分上游域名（raw.githubusercontent）经企业代理可能握手超时；key 库随包分发即为规避此问题。

### 2.6 故障恢复（常见错误对照）

| 现象 | 原因 | 处理 |
|---|---|---|
| `Failed building depot dependency (Invalid content configuration)` / state `0x202`，下载不动 | `appinfo.vdf` 冻结在旧时刻，与内存 depot 依赖不一致（多次强杀/卸载后常见） | 退出 Steam → 备份并删除 `D:\STEAM\appcache\appinfo.vdf`、`appcache\appinfo\`、`opensteamtool\pattern\`、`opensteamtool\ipc\` → 冷启动 Steam 自动重建。**本次即靠此解决** |
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

### A · 联机启动
- `启动Steam_联机.bat`：带 `-onlinefix` 参数启动（**仅限** 2.2 表 A 类 Steamworks 大厅游戏）
- 前提：完全退出 Steam 再运行；同一时间只能一个此类联机游戏

### A · 防封号开关
- `ost_toggle.bat` 菜单 [2]：移走 Steam 目录里的三个 DLL，恢复纯净 Steam。玩 VAC / 竞技游戏前**务必先执行**。

### B · 家庭共享内存解锁（按需）
- 完全退出 Steam → 以管理员身份运行 `SteamFamilyUnlock.exe`
- 它会启动 Steam、等 DLL 注入、patch 内存、进入守护；关掉 Steam 自动结束
- `--clean` 参数：仅移走 Steam 目录里的 OST DLL
- 注意：实测内存 patch 赢不了服务器踢人，这条路线大部分情况只是兜底残留，优先级低于"先入库"

### Denuvo 助手（半自动）
```
python denuvo_helper.py 3489700            # 查这个 Denuvo 游戏该怎么过运行关
python denuvo_helper.py 3489700 --ticket HEX  # 填 AppTicket
python denuvo_helper.py 3489700 --apply      # 写入带票据槽位的 Lua 块
```

---

## 五、从源码打包 exe（可选）

改了 `.py` 之后需重新打包才影响 exe：

```bat
REM A · 简单入库.exe
py -m PyInstaller --noconfirm --clean --onefile --windowed --name SimpleImport --distpath dist --workpath build --specpath . 简单入库.py
REM 把 dist\SimpleImport.exe 重命名为 简单入库.exe

REM B · SteamFamilyUnlock.exe
python build_exe.py
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
  steam_unlock_launcher.py  内存 patch 启动器（B）
  build_exe.py              打包 B 的脚本
  _detect_steam.bat         bat 共用的 Steam 路径探测
  OST管理面板.bat / 启动Steam_联机.bat / ost_toggle.bat
  ost_dll\                  三个注入 DLL（主版，随 B 打包内嵌）
  depotkeys_master.json     ManifestHub 全量 key 库（16MB / 288381 条，随包分发）
  简单入库.exe / SteamFamilyUnlock.exe   两个现成 exe
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
- OpenSteamTool：github.com/OpenSteam001/OpenSteamTool（主版）
