# SDD ledger — plan: D:\STEAM入库\全自动入库_v2\docs\superpowers\plans\2026-11-23-入库中心v2.md

执行方式：本会话 inline（executing-plans），用户 m02638 跳过执行方式选择，方向已在 m02581 授权。
Spec: D:\STEAM入库\全自动入库_v2\docs\superpowers\specs\2026-11-23-入库中心v2-design.md（已批准，含附录 A）。
状态：**全部完成（T1–T6）**，2026-11-23 交付。详见 `验收记录.md`。

Rulings:
- 无 git 仓库（Global Constraints 明确不建）：git 系 task-start/task-done 脚本不可用，改用本 ledger 文件 + todo 追踪进度；TDD 红绿步骤与验收证据完整保留。 — 成本：没有 git diff/commit 做最终审查基线，改用文件快照与逐任务测试输出留底。
- 用户 m02638 跳过执行方式选择：两个选项都是"执行"且方向已授权，采用本会话顺序执行 + TDD。 — 成本：上下文消耗较大，靠 ledger 与压缩恢复。
- pytest 未安装 → pip install pytest 9.2.0 成功（exit 1 仅为 PATH warning），测试按计划用 pytest 不变。 — 成本：多一个开发依赖，不打包进 exe。
- T6 onefile 打包：中文 `--name` 会让 PyInstaller 失败，改用英文名 `RukuCenter`；ps1 在 PowerShell 编码下把中文路径读坏，改内联 pwsh 命令打包。 — 成本：build.ps1 保留作参考但实际用内联命令。
- T6 GUI 冒烟：onefile `Start-Process` 返回 bootloader 父进程（Handle=0 无标题），真正 GUI 是子进程；改用按 `MainWindowTitle` 枚举确认窗口存在。 — 成本：冒烟脚本要按标题找子进程。

Pre-flight 接口扫描:
- T2 产出 `AA.*`/`V.*` 签名 → T5 消费：计划已按 v1 真实签名核对（build_block/judge/resolve/fetch_app_info/upsert_lock_block 等），无冲突。
- T1 产出 `paths.*` → T2/T3/T4/T5 消费：签名一致（find_steam_dir/lua_path/resource_dir/writable_dir/steam_running）。
- T3 产出 `game_index.search/add_name` → T5 消费：一致。
- T4 产出 `backup.snapshot/rollback/health_check/audit` → T5 消费：一致。
- 共享 data 目录（writable_dir）由 T1 定义，T2/T3/T4 都从它定位数据文件：无写冲突（各用不同文件名）。

Task 1: complete — tests: pytest tests/test_paths.py → 8 passed；真机校验 Steam=d:\steam，AutoLoginUser=smallmonstercat(accountid 732831206)，lua=d:\steam\config\stplug-in\mygames.lua。

Task 2: complete — tests: pytest tests/test_modules.py → 4 passed。四模块去硬编码（auto_adapt/version_lock/apply_patch/denuvo_helper），数字 GID 写法保留，缺 key 库不联网降级。真机 KEYS=288381，剑星块数字 GID=True。

Task 3: complete — tests: pytest tests/test_game_index.py → 3 passed。game_index.py 本地名字检索 + storesearch 补查，names.json 9 条。

Task 4: complete — tests: pytest tests/test_backup.py → 3 passed。backup.py 快照/回滚（强制退 Steam）/体检/审计；真机体检 36 块配对、三 DLL 全 OK。

Task 5: complete — tests: pytest tests/test_main_app.py → 2 passed。main_app.py 4 tab GUI（入库/版本锁定/补丁/备份与隔离），重活线程化；源码冒烟 4 tab + 36 入库项 + 1 破解项。

Task 6: complete — 打包 `入库中心.exe`（21.6MB，SHA256 8B162D1F...1598916）+ 数据文件外置；GUI 冒烟窗口标题正常；隔离验收脚本 6 项 ALL_OK；v1 基线 7 文件哈希不变；写 `验收记录.md` + `使用说明.md`；临时调试产物已清理。
- 全量回归：20 passed in 0.59s；8 模块 py_compile ALL COMPILE OK。
