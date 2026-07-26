# 打包与分发指南

SSHFerry 桌面端使用 [PyInstaller](https://pyinstaller.org/) 打包为单文件可执行程序。仓库根目录的 `SSHFerry.spec` 是跨平台通用的构建描述,Windows、macOS、Linux 三端共用同一份。

## 版本号

版本号来自 `pyproject.toml` 的 `version` 字段,构建脚本和 CI 都从这里读取。发布前先更新它,并打一个 `v<版本号>` 的 git tag —— `.github/workflows/release.yml` 由该 tag 触发,自动在三端构建产物。

## Windows

推荐用现成脚本(内含 PyInstaller 警告校验和产物校验):

```powershell
powershell -ExecutionPolicy Bypass -File ./tools/build_windows.ps1 -Clean -VenvPath .venv_compat
```

产物:

```text
release/SSHFerry-<版本>-windows/SSHFerry.exe
release/SSHFerry-<版本>-windows.zip
release/SSHFerry-<版本>-windows.sha256
```

**代码签名**:当前产物未签名,首次运行会触发 SmartScreen 拦截。要签名,需一张代码签名证书(EV 证书体验最佳),在打包后对 `SSHFerry.exe` 执行 `signtool sign`。CI 中已在 `release.yml` 的 Windows 任务预留了插入 signtool 步骤的位置,证书应存为仓库 secret。

## macOS

```bash
pip install -r requirements.txt pyinstaller
python -m PyInstaller SSHFerry.spec --noconfirm
```

产物在 `dist/SSHFerry`。

**签名与公证**:未签名的应用在新版 macOS 上会被 Gatekeeper 拦截,用户需右键 → 打开。正式分发需要:

1. Apple Developer ID 证书,`codesign --deep --options runtime` 签名;
2. 用 `notarytool` 提交公证并 `stapler staple` 装订票据。

这两步需要 Apple 开发者账号和 app-specific 密码(存为仓库 secret)。`release.yml` 的 macOS 任务已预留插入位置。

## Linux

```bash
pip install -r requirements.txt pyinstaller
python -m PyInstaller SSHFerry.spec --noconfirm
```

产物在 `dist/SSHFerry`,是一个自包含的 ELF 可执行文件。运行前需确保系统有 Qt 依赖的图形库(无桌面环境的服务器需要):

```bash
sudo apt-get install -y libegl1 libgl1 libxkbcommon0 libdbus-1-3
```

也可以不打包,直接从源码运行:

```bash
pip install -r requirements.txt
./run.sh
```

## CI 自动构建

- `.github/workflows/ci.yml`:每次 push / PR 跑测试(含覆盖率门槛)、lint、前端构建,以及针对真实 sshd 的端到端传输校验。
- `.github/workflows/release.yml`:push `v*` tag 时触发,三端并行构建并上传产物(Windows 走打包脚本,macOS/Linux 走跨平台 spec)。签名步骤待证书 secret 就绪后接入。

## 签名现状小结

| 平台 | 打包 | 签名 |
| --- | --- | --- |
| Windows | ✅ 脚本 + CI | ⏳ 待证书(signtool 位置已预留) |
| macOS | ✅ CI | ⏳ 待 Developer ID(codesign/notarytool 位置已预留) |
| Linux | ✅ CI | 不适用(Linux 无强制签名) |
