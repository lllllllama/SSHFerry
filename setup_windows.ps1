# Windows 环境快速设置脚本
# 使用 PowerShell 运行

Write-Host "正在设置 SSHFerry 开发环境..." -ForegroundColor Green

# 1. 删除旧的虚拟环境（如果存在）
if (Test-Path ".venv") {
    Write-Host "删除旧的虚拟环境..." -ForegroundColor Yellow
    Remove-Item -Recurse -Force .venv -ErrorAction SilentlyContinue
}

# 2. 创建新的虚拟环境
Write-Host "创建虚拟环境..." -ForegroundColor Green
python -m venv .venv

# 3. 激活虚拟环境
Write-Host "激活虚拟环境..." -ForegroundColor Green
& .\.venv\Scripts\Activate.ps1

# 4. 升级 pip
Write-Host "升级 pip..." -ForegroundColor Green
python -m pip install --upgrade pip

# 5. 安装 PySide6
Write-Host "安装 PySide6..." -ForegroundColor Green
pip install --index-url https://pypi.org/simple/ PySide6==6.6.1

# 6. 安装其他依赖
Write-Host "安装其他依赖..." -ForegroundColor Green
pip install paramiko pytest ruff

Write-Host ""
Write-Host "✅ 环境设置完成！" -ForegroundColor Green
Write-Host ""
Write-Host "现在可以运行应用:" -ForegroundColor Cyan
Write-Host "  .\run.bat" -ForegroundColor Yellow
Write-Host ""
Write-Host "或者手动激活虚拟环境:" -ForegroundColor Cyan
Write-Host "  .\.venv\Scripts\Activate.ps1" -ForegroundColor Yellow
Write-Host "  python -m src.app.main" -ForegroundColor Yellow
