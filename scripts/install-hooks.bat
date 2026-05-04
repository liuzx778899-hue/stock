@echo off
REM 安装 Git hooks 到 .git/hooks/

echo 安装 Git hooks...

copy /Y "%~dp0hooks\post-commit" ".git\hooks\"
copy /Y "%~dp0hooks\pre-push" ".git\hooks\"
copy /Y "%~dp0hooks\commit-msg" ".git\hooks\"

echo.
echo ✅ Git hooks 已安装:
echo    - post-commit: 解析任务编号 → 更新 agent-tasks.md
echo    - pre-push: 运行 pytest → 测试失败阻止推送
echo    - commit-msg: 验证 commit 格式
echo.
echo Commit 规范: feat: xxx #54-T1
