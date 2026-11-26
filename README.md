# Steam 入库管家（入库中心 v2 + 本体监控 v3）

> **一句话结论（务必先读）：这套工具能自动把游戏"加进库并下载"，但能不能真正玩，取决于游戏本身的验证机制。最终只有「纯单机」和少数「Steam PVE 合作老游戏」能稳定玩。带自有账号、内核反作弊、第三方联机后端、或 Denuvo 未破解的游戏，工具再自动也救不回来。**

单 exe、零硬编码路径（自动找 Steam）、pywebview + 系统 WebView2 界面（4 套主题），零中心化服务、零遥测。内置 v3 启动自检：只报不改地监控已锁定破解游戏的本体更新。

## 快速开始

1. 双击 `入库中心_v2_v3/入库管家.exe`（约 22MB，无需装 Python；界面用系统自带 WebView2，Win10/11 已内置）。
2. **1 入库** tab：输入游戏名 / AppID / 商店链接 →「搜索名字」→ 双击结果卡片填入 AppID →「+ 入库」；入库后**完全重启 Steam**（托盘右键退出，不是关窗口）。
3. Denuvo 破解游戏走 **2 版本锁定** tab → **3 补丁** tab 流程，见下方「破解游戏完整流程」。

详细界面说明见 [`入库中心_v2_v3/使用说明.md`](入库中心_v2_v3/使用说明.md)。

## 四个 tab

| tab | 作用 |
|---|---|
| **1 · 入库** | 搜索 AppID、写入 `mygames.lua`、封面卡片墙、状态三态（绿=可下载可运行 / 黄=需票据或补丁 / 红=key 库无记录下载不了） |
| **2 · 版本锁定** | 导入破解包挖历史锁定 GID 写进 lua；应用锁定；**一键冷启动**（关 Steam→备份删缓存→重开）；本体版本变化告警 |
| **3 · 补丁** | 扫描预览（dry-run）后把破解文件覆盖进游戏目录，覆盖前自动备份可回滚 |
| **4 · 备份隔离** | 账号配置快照、配置体检、一键回滚（强制先退 Steam） |

主题：深色·Midnight（默认）/ 浅色·Daylight / 深色·Nord / 浅色·Solarized，选择记在 exe 同目录 `ui_prefs.json`。

## 三关模型：入库 ≠ 能玩

| 关卡 | 通过条件 | 自动化程度 |
|---|---|---|
| **① 下载** | 该游戏存在公开的 depot key + manifest | ✅ 全自动（28.8 万 key 库 + 实时 manifest） |
| **② 运行** | 无 DRM，或有 Denuvo 但票据/补丁已就位 | ⚠️ 无 DRM 直接过；Denuvo 需锁旧版 + 打补丁（人工下载补丁） |
| **③ 联机** | Steamworks 票据有效，且无自有账号/内核反作弊 | ❌ 仅 Steam lobby 类可修，其余多数无解 |

典型能玩的（三关全通）：求生之路2、Hades/Hades II、空洞骑士、星露谷物语、Terraria 等**纯单机或 Steam PVE 合作老游戏**。

**联机分类**：A·Steamworks 大厅（可修）；B·第三方后端如 Photon（需游戏专用 mod，不稳）；C·自有账号 + 内核反作弊（EA / Xbox Live / 育碧，**无解，联机必封号**）。

## Denuvo 破解游戏完整流程（以剑星为例）

适用：有历史破解补丁的纯单机 Denuvo 游戏。核心是「锁到破解版对应的旧版本 → 下完覆盖补丁」。

1. **2 版本锁定** tab →「破解包路径」框粘贴破解包自带的**锁定版 lua**（含 `setManifestid` 的那个）路径，或点「浏览…」选它 →「导入破解包」。普通 `3489700.lua`（只有 `addappid`）挖不到 GID。
2. 选中该游戏 →「应用锁定到入库清单」（数字写法写 `setManifestid`）。
3. 点「一键冷启动」——自动关 Steam（含 webhelper/crashhandler）、备份并删 `appinfo.vdf` + `appcache\appinfo`、冷启动 Steam。备份落在 `backup\appinfo_时间戳\`。
4. 核对 `Steam安装目录\logs\content_log.txt` 里 `Downloading ... (锁定 GID)`，确认是锁定值（剑星 3489701=`2747626496734343426`）而非实时值，等下载完。
5. **3 补丁** tab → 补丁包路径选 `_crack_ready` 目录或 zip →「扫描预览」核对 →「确认覆盖」→ 关 Steam 直接运行游戏验证（补丁自带 `steam_api64.dll` emu，不依赖 Steam 票据）。

> `setManifestid` 第一参数必须是**数字**，写成字符串会被 Steam 静默忽略。

## 已知边界

- **VAC 封号风险**：玩 VAC / 竞技游戏前必须彻底移走 Steam 目录的三个注入 DLL，恢复纯净 Steam。**破解游戏别进多人模式。**
- **两套注入不能共存**：SteamTools 与 OpenSteamTool 都劫持 `xinput1_4.dll`。SteamTools 会把锁定的历史 GID 覆盖回最新版，导致 `Missing decryption key`。二选一，本工具走纯 OST。
- **Steam 大版本更新**后 OST 的 hook pattern 需上游跟上（联网自动拉），期间入库功能可能短暂失效；已落盘游戏/补丁不受影响。
- 破解游戏建议关闭自动更新，否则本体更新会让锁定 GID 失效（v3 启动自会告警）。
- 只适用于无反作弊 / 纯单机 / Steamworks 票据可解的游戏；EA/Ubisoft/Xbox Live 自有账号 + 内核反作弊游戏无解。
- 家庭库显示：账号在家庭组时假入库游戏会显示"来自家庭库"，这是 Steam 服务端账本判定，本地改不了。日志里 `failed to update ownership ticket (Access Denied)` 是 OST 固有噪音，与下载成败无关。

## 故障恢复对照

| 现象 | 原因 | 处理 |
|---|---|---|
| `Invalid content configuration` / state `0x202`，下载不动 | `appinfo.vdf` 与内存 depot 依赖不一致 | 用「一键冷启动」自动清缓存重建 |
| `Missing decryption key` | 实际下载 GID 与 key/锁版不匹配（多因 SteamTools 覆盖回最新 GID，或 setManifestid 写成字符串） | 确保纯 OST + `setManifestid(数字,"gid")` + 冷启动 |
| 下载到最新版而非锁定版 | setManifestid 第一参数写成字符串被忽略 | 用数字写法（工具已修正） |
| 加游戏后 Steam 里看不到 | 未重启 Steam | 托盘右键完全退出再启动 |

## 目录结构

```
README.md                        本说明
入库中心_v2_v3/
  入库管家.exe                   现成 exe（21MB，双击即用）
  使用说明.md                    界面逐项说明
  RukuCenter.spec                PyInstaller 打包配置
  build.ps1                      重新打包脚本
  src/                           源码 + 打包资源
    main_app.py                  pywebview 界面层 / js_api 桥
    paths.py                     路径探测 / Steam 进程控制 / 缓存清理
    auto_adapt.py  version_lock.py  apply_patch.py  backup.py
    game_index.py  denuvo_helper.py  update_guard.py
    ui/index.html                单文件前端（改界面只动这里）
    app.ico                      图标
    depotkeys_master.json        全量 depot key 库（16MB / 288381 条，随包分发）
    crack_library.json           破解游戏库（GID 锁定值）
    names.json                   游戏名↔AppID 索引
  tests/                         单元测试（pytest）
```

> 3 个 json 已打进 exe，exe 同级无需预置即可运行；要单独更新 key 库时把新版 `depotkeys_master.json` 拷到 exe 同级即可优先读取。`covers\`（封面缓存）、`ui_prefs.json`、`ui_error.log`、`baseline.json`、`audit.log`、`backup\` 均为运行时生成，不入仓库。

## 数据与隐私

不含任何账号、家庭组、appinfo 缓存等私有数据；16MB key 库随仓库分发（clone 即用，规避代理下载问题），运行时可联网刷新。零中心化服务、零遥测，全部逻辑在本地。

## 从源码打包（可选）

改了 `.py` 后需重新打包才影响 exe：在 `入库中心_v2_v3/` 下执行 `powershell -File build.ps1`（自动找脚本所在目录，产出 `入库管家.exe`）。PyInstaller onefile + `--windowed`，3 json / ui / ico 由 spec 打进 exe。

## 外部信源

- depot key：github.com/SteamAutoCracks/ManifestHub
- manifest / depot 元数据：api.steamcmd.net
- DRM 判断：store.steampowered.com/api/appdetails
- 历史 GID / 破解版本：社区破解包内的锁定版 lua
- OpenSteamTool：github.com/OpenSteam001/OpenSteamTool（官方主版）
