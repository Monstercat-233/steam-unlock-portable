# Steam 全自动入库 + 家庭共享解锁工具（可移植版）

一套配合 OpenSteamTool 使用的 Windows 工具，两大部分职责分离：

| 部分 | 交付物 | 职责 |
|---|---|---|
| **A · 全自动入库** | `简单入库.exe`（GUI）/ `addgame_pro.py`（命令行） | 输入游戏名或 AppID → 自动联网取 depot key + 实时 manifest + DRM 判断 → 幂等写入 Steam 的 `mygames.lua` |
| **B · 家庭共享解锁启动器** | `SteamFamilyUnlock.exe` | 用 schtasks 跳板启动 Steam → 内存 patch（`CUser::UpdateFamilyRunningApps` NOP）→ 守护重 patch。DLL 常驻。 |

> 入库/下载层（A）和内存 patch 层（B）是两个不同层，互不重复。日常只用得到 A；只有在需要内存解锁时才用 B。

---

## 一、它做什么 / 不做什么

**能自动：**
- 按游戏名/AppID/商店链接解析 AppID（本地表 → Steam storesearch API）
- 从 steamcmd.net 拉该游戏全部 depot 列表 + 每个 depot 的实时 manifest GID
- 从 ManifestHub 全量 depot key 库（首次自动下载约 16MB / 28 万条，本地缓存 7 天刷新）取每个 depot 的解密 key
- 从 Steam appdetails 读 Denuvo / VAC / 发行商，给出「能否下载 / 运行 / 联机」判断
- 生成带唯一标记的幂等 Lua 块：重复添加覆盖式写入，不留孤儿行

**不能自动（需人工）：**
- Denuvo 提票（需真拥有者账号 `extract_tickets`，票据 30 分钟有效）或打绕过补丁
- 第三方联机后端（Photon 等）或自有账号+反作弊（EA / 微软 / 育碧）的联机

三关判断：**①下载**需公开 depot key + manifest；**②运行**需无 Denuvo 或票据/补丁；**③联机**需 Steam 票据（`Steamworks` 类可用 `-onlinefix`；`Photon` 类需游戏专用 mod；自有账号+内核反作弊无解）。

---

## 二、安装（换一台新电脑）

### 前置
- Windows + Steam（能正常登录）
- Python 3.10+（仅源码运行/打包时需要；用现成 exe 不需要）
- 联网（首次会自动下载 16MB key 库；走系统代理）

### 步骤
1. 把整个目录放到任意位置（例：`D:\tools\steam-unlock\`）
2. **把 `config_template\opensteamtool.toml` 复制到 Steam 安装目录**（与 `steam.exe` 同级），文件名不变
3. **把 `src\ost_dll\` 里的三个 DLL**（`dwmapi.dll` / `xinput1_4.dll` / `OpenSteamTool.dll`）复制到 Steam 安装目录
   - 也可用 `ost_toggle.bat` 菜单 [1] 自动复制（需先完全退出 Steam）
4. 完全退出并重启 Steam 一次

Steam 目录无需手动指定：工具按以下顺序自动探测——环境变量 `STEAM_PATH` → 注册表 → 正在运行的 steam.exe → 常见安装目录。若自动探测失败，设一个环境变量 `STEAM_PATH=D:\你的Steam目录` 即可。

---

## 三、使用

### A · 入库（日常只用这个）

**GUI：** 双击 `简单入库.exe`
- 输入框填游戏名或 AppID → 点「添加入库」
- 下方列表是已入库的主游戏 AppID；可「移除选中」「刷新」
- 状态栏会显示能否下载、有无 Denuvo 等判断
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
- `启动Steam_联机.bat`：带 `-onlinefix` 参数启动（Steamworks 大厅类联机）
- 前提：完全退出 Steam 再运行；同一时间只能一个此类联机游戏

### A · 防封号开关
- `ost_toggle.bat` 菜单 [2]：移走 Steam 目录里的三个 DLL，恢复纯净 Steam。玩 VAC / 竞技游戏前**务必先执行**。

### B · 家庭共享内存解锁（按需）
- 完全退出 Steam → 以管理员身份运行 `SteamFamilyUnlock.exe`
- 它会启动 Steam、等 DLL 注入、patch 内存、进入守护；关掉 Steam 自动结束
- `--clean` 参数：仅移走 Steam 目录里的 OST DLL

### Denuvo 助手（半自动）
```
python denuvo_helper.py 3489700            # 查这个 Denuvo 游戏该怎么过运行关
python denuvo_helper.py 3489700 --ticket HEX  # 填 AppTicket
python denuvo_helper.py 3489700 --apply      # 写入带票据槽位的 Lua 块
```

---

## 四、从源码打包 exe（可选）

改了 `.py` 之后需重新打包才影响 exe：

```bat
REM A · 简单入库.exe
py -m PyInstaller --noconfirm --clean --onefile --windowed --name SimpleImport --distpath dist --workpath build --specpath . 简单入库.py
REM 把 dist\SimpleImport.exe 重命名为 简单入库.exe

REM B · SteamFamilyUnlock.exe
python build_exe.py
```

注意：`steam_path.py` 必须和主脚本一起打包（PyInstaller 会自动跟踪 import）。

---

## 五、目录结构

```
src/
  steam_path.py           统一路径探测（无硬编码，核心）
  auto_adapt.py           全自动适配核心（key/manifest/DRM）
  简单入库.py / addgame_pro.py / addall.py / denuvo_helper.py
  steam_unlock_launcher.py  内存 patch 启动器（B）
  build_exe.py            打包 B 的脚本
  _detect_steam.bat       bat 共用的 Steam 路径探测
  OST管理面板.bat / 启动Steam_联机.bat / ost_toggle.bat
  ost_dll\                三个注入 DLL（随 B 打包内嵌）
config_template/
  opensteamtool.toml      配置模板（复制到 Steam 目录）
```

---

## 六、数据与隐私
- 不含任何账号、家庭组、appinfo 缓存等私有数据
- 16MB key 库不随仓库分发，首次运行从 ManifestHub 自动下载
- 运行时生成的缓存（`auto_adapt_cache.json`、`depotkeys_master.json`）均已在 `.gitignore` 排除

## 七、外部信源
- depot key：github.com/SteamAutoCracks/ManifestHub
- manifest / depot 元数据：api.steamcmd.net
- DRM 判断：store.steampowered.com/api/appdetails
- OpenSteamTool：github.com/OpenSteam001/OpenSteamTool（主版）
