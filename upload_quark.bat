@echo off
chcp 65001
setlocal enabledelayedexpansion

:: === 构造今日日期 ===
for /f %%i in ('powershell -NoLogo -Command "Get-Date -Format yyyyMMdd"') do set DATESTR=%%i

:: === 路径设置 ===
set "SRC_DIR=C:\Users\Administrator\Desktop\screens\%DATESTR%"
set "ZIP_PATH=C:\Users\Administrator\Desktop\screens\%DATESTR%.zip"

:: === 压缩目录为 zip ===
powershell -Command "Compress-Archive -Path '%SRC_DIR%\*' -DestinationPath '%ZIP_PATH%' -Force"

:: === 打开夸克网盘（Edge 浏览器）===
start msedge "https://pan.quark.cn"

:: === 等待网页加载，启动 AHK 脚本 ===
timeout /t 5 >nul
start "" "%~dp0upload_quark.ahk"

:: 等待上传完成
timeout /t 120

:: 上传成功后删除本地资源
del /f /q "%ZIP_PATH%"
rmdir /s /q "%SRC_DIR%"

endlocal
pause
