@echo off
chcp 65001
setlocal enabledelayedexpansion

:: === 确定项目根目录 ===
:: %~dp0 是当前脚本所在目录 (一般在 ...\utils\)
:: 加上 \.. 就能回到项目根目录
set "ROOT_DIR=%~dp0.."

:: === 构造今日日期 ===
for /f %%i in ('powershell -NoLogo -Command "Get-Date -Format yyyyMMdd"') do set DATESTR=%%i

set "SCREEN_DIR=%ROOT_DIR%\logs\screens"
:: === 路径设置 ===
set "SRC_DIR=%SCREEN_DIR%\%DATESTR%"
set "ZIP_PATH=%SCREEN_DIR%\%DATESTR%.zip"

:: === 压缩目录为 zip ===
powershell -Command "Compress-Archive -Path '%SRC_DIR%\*' -DestinationPath '%ZIP_PATH%' -Force"

:: === 打开夸克网盘（Edge 浏览器）===
start "" /MAX msedge "https://pan.quark.cn"

:: === 等待网页加载，启动 AHK 脚本 ===
timeout /t 5 >nul
start "" "%ROOT_DIR%\ahk\upload_quark.ahk"

:: 等待上传完成
timeout /t 120

endlocal
pause
