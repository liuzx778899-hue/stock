@echo off
chcp 65001 >nul
setlocal enabledelayedexpansion

echo ============================================
echo    A股数据采集系统 - 代理绕过规则设置工具
echo ============================================
echo.
echo 此工具将配置系统代理绕过规则，使东方财富数据源能够正常连接
echo.

:: 检查是否以管理员身份运行
net session >nul 2>&1
if %errorlevel% neq 0 (
    echo [警告] 请以管理员身份运行此脚本！
    echo 右键点击此文件，选择"以管理员身份运行"
    echo.
    pause
    exit /b 1
)

:: 要添加的域名列表
set "DOMAINS=eastmoney.com;push2.eastmoney.com;push2his.eastmoney.com;17.push2.eastmoney.com;82.push2.eastmoney.com;emdata.eastmoney.com"

:: 设置环境变量（当前用户）
echo [1] 设置用户环境变量 no_proxy...
setx no_proxy "%DOMAINS%" >nul
setx NO_PROXY "%DOMAINS%" >nul
echo     完成

:: 设置系统环境变量
echo [2] 设置系统环境变量 no_proxy...
setx /M no_proxy "%DOMAINS%" >nul
setx /M NO_PROXY "%DOMAINS%" >nul
echo     完成

:: 设置 Internet Explorer 代理绕过规则（影响系统代理）
echo [3] 设置 IE/系统代理绕过规则...
reg add "HKCU\Software\Microsoft\Windows\CurrentVersion\Internet Settings" /v ProxyOverride /t REG_SZ /d "%DOMAINS%;<local>" /f >nul
echo     完成

:: 尝试设置 WinHTTP 代理绕过
echo [4] 设置 WinHTTP 代理配置...
netsh winhttp set proxy proxy-server="direct" bypass-list="%DOMAINS%" >nul 2>&1
echo     完成

echo.
echo ============================================
echo    设置完成！
echo ============================================
echo.
echo 已添加的绕过域名：
echo %DOMAINS%
echo.
echo [注意] 请重启命令行窗口或重新打开程序使环境变量生效
echo [建议] 如果仍有问题，请完全关闭代理软件后重新运行采集
echo.
pause