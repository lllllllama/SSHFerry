# SSHFerry 环境设置脚本 (Conda 环境)
# 运行此脚本来安装所有依赖

Write-Host "=== SSHFerry 环境设置 ===" -ForegroundColor Green
Write-Host ""

# 激活 sshferry 环境
Write-Host "正在激活 sshferry 环境..." -ForegroundColor Cyan
conda activate sshferry

if ($LASTEXITCODE -ne 0) {
    Write-Host "❌ 无法激活 sshferry 环境" -ForegroundColor Red
    Write-Host "请先运行: conda create -n sshferry python=3.11 -y" -ForegroundColor Yellow
    exit 1
}

Write-Host "✅ 环境已激活" -ForegroundColor Green
Write-Host ""

# 升级 pip
Write-Host "正在升级 pip..." -ForegroundColor Cyan
python -m pip install --upgrade pip

# 安装 PySide6
Write-Host ""
Write-Host "正在安装 PySide6..." -ForegroundColor Cyan
pip install PySide6==6.6.1

# 安装其他依赖
Write-Host ""
Write-Host "正在安装其他依赖..." -ForegroundColor Cyan
pip install paramiko pytest ruff

Write-Host ""
Write-Host "=== 安装完成 ===" -ForegroundColor Green
Write-Host ""
Write-Host "验证安装..." -ForegroundColor Cyan
python -c "from PySide6.QtWidgets import QApplication; print('✅ PySide6 导入成功')"
python -c "from src.ui.main_window import MainWindow; print('✅ 所有模块加载成功')"

Write-Host ""
Write-Host "🎉 环境设置完成！" -ForegroundColor Green
Write-Host ""
Write-Host "现在可以运行应用:" -ForegroundColor Cyan
Write-Host "  .\run.bat" -ForegroundColor Yellow
Write-Host ""
Write-Host "或手动激活环境:" -ForegroundColor Cyan
Write-Host "  conda activate sshferry" -ForegroundColor Yellow
Write-Host "  python -m src.app.main" -ForegroundColor Yellow
