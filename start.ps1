# A股数据采集系统 - 启动脚本
# 用法: PowerShell 中运行 ./start.ps1

param(
    [string]$Mode = "all",      # all | backend | frontend
    [string]$DBPassword = ""
)

$ErrorActionPreference = "Stop"

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  A股数据采集系统启动脚本" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# 设置数据库密码
$env:DB_PASSWORD = $DBPassword
Write-Host "[OK] 数据库密码已设置" -ForegroundColor Green

# 检查 Python
if (-not (Get-Command python -ErrorAction SilentlyContinue)) {
    Write-Host "[ERROR] 未找到 Python，请先安装" -ForegroundColor Red
    exit 1
}
Write-Host "[OK] Python 已安装" -ForegroundColor Green

# 检查 Node.js（仅前端模式需要）
if ($Mode -eq "frontend" -or $Mode -eq "all") {
    if (-not (Get-Command npm -ErrorAction SilentlyContinue)) {
        Write-Host "[ERROR] 未找到 Node.js/npm，请先安装" -ForegroundColor Red
        exit 1
    }
    Write-Host "[OK] Node.js/npm 已安装" -ForegroundColor Green
}

# 检查依赖是否已安装
$projectRoot = $PSScriptRoot

# Python 依赖
if (-not (Test-Path "$projectRoot\requirements.txt")) {
    Write-Host "[ERROR] 未找到 requirements.txt" -ForegroundColor Red
    exit 1
}

Write-Host ""
Write-Host "启动模式: $Mode" -ForegroundColor Yellow
Write-Host ""

switch ($Mode) {
    "backend" {
        Write-Host "启动后端 API..." -ForegroundColor Yellow
        Set-Location $projectRoot
        python web_app.py
    }

    "frontend" {
        Write-Host "启动前端开发服务器..." -ForegroundColor Yellow
        Set-Location "$projectRoot\frontend"
        npm run dev
    }

    "all" {
        Write-Host "同时启动后端 + 前端..." -ForegroundColor Yellow
        Write-Host ""

        # 启动后端（后台）
        Write-Host "[1] 启动后端 API (http://localhost:8000)" -ForegroundColor Yellow
        $backendJob = Start-Job -ScriptBlock {
            param($path, $pwd)
            $env:DB_PASSWORD = $pwd
            Set-Location $path
            python web_app.py
        } -ArgumentList $projectRoot, $DBPassword

        # 等待后端启动
        Start-Sleep -Seconds 3

        # 启动前端（后台）
        Write-Host "[2] 启动前端开发服务器 (http://localhost:3000)" -ForegroundColor Yellow
        $frontendJob = Start-Job -ScriptBlock {
            param($path)
            Set-Location "$path\frontend"
            npm run dev
        } -ArgumentList $projectRoot

        Write-Host ""
        Write-Host "========================================" -ForegroundColor Green
        Write-Host "  服务已启动!" -ForegroundColor Green
        Write-Host "========================================" -ForegroundColor Green
        Write-Host ""
        Write-Host "  前端: http://localhost:3000" -ForegroundColor White
        Write-Host "  后端: http://localhost:8000" -ForegroundColor White
        Write-Host "  API文档: http://localhost:8000/docs" -ForegroundColor White
        Write-Host ""
        Write-Host "  按 Ctrl+C 停止所有服务" -ForegroundColor Yellow
        Write-Host ""

        # 等待用户中断
        try {
            while ($true) {
                # 显示后端输出
                $backendOutput = Receive-Job -Job $backendJob -ErrorAction SilentlyContinue
                if ($backendOutput) {
                    Write-Host "[Backend] $backendOutput" -ForegroundColor Gray
                }

                # 显示前端输出
                $frontendOutput = Receive-Job -Job $frontendJob -ErrorAction SilentlyContinue
                if ($frontendOutput) {
                    Write-Host "[Frontend] $frontendOutput" -ForegroundColor Gray
                }

                Start-Sleep -Milliseconds 500
            }
        }
        finally {
            Write-Host ""
            Write-Host "正在停止服务..." -ForegroundColor Yellow
            Stop-Job -Job $backendJob -ErrorAction SilentlyContinue
            Stop-Job -Job $frontendJob -ErrorAction SilentlyContinue
            Remove-Job -Job $backendJob -ErrorAction SilentlyContinue
            Remove-Job -Job $frontendJob -ErrorAction SilentlyContinue
            Write-Host "[OK] 服务已停止" -ForegroundColor Green
        }
    }

    default {
        Write-Host "[ERROR] 无效的模式: $Mode" -ForegroundColor Red
        Write-Host "用法: ./start.ps1 -Mode all|backend|frontend" -ForegroundColor Yellow
        exit 1
    }
}