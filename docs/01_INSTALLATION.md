# 安装与更新

## macOS 开发/演示机

双击 `BPlus Experiment.command` 可使用已有开发环境启动 GUI。要建立冻结的实验环境：

```bash
./scripts/setup_environment.sh
```

脚本只创建或复用 `.venv-exp`，不删除 `.venv`。安装后执行：

```bash
.venv-exp/bin/python scripts/check_environment.py --profile experiment
```

安装器默认把 uv 缓存放在项目内的 `.uv-cache`，避免 macOS/Codex 环境对 `~/.cache` 的权限限制。可通过 `UV_CACHE_DIR` 覆盖。

> 依赖均已安装但磁盘不足 20 GiB 时，审计会返回 FAIL；这是 REAL 模式的数据安全门槛，不影响 DEMO/PILOT 软件练习。

## Windows 实验机

安装 uv 和厂商驱动后，在 PowerShell 中运行：

```powershell
.\scripts\setup_environment.ps1
```

PsychoPy/LSL 安装成功不等于 TTL 已验证。并口、LabJack、CURRY、LIGHTNIRS 和 aSee 驱动必须按现场文档验证。

## SeetaPsych

为避免影响呈现时序，按 `SEETAPSYCH_INTEGRATION.md` 建立独立离线分析环境。
