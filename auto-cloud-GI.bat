@echo off
chcp 65001
setlocal enabledelayedexpansion
:: 缓冲10秒，以在不想执行时取消
timeout /t 10 >nul
:: 获取当前 .bat 所在目录
set "BAT_DIR=%~dp0"
set "CONFIG_FILE=%BAT_DIR%config.ini"

:: 读取 config.ini 中的路径配置
for /f "tokens=1,* delims==" %%A in ('findstr "=" "%CONFIG_FILE%"') do (
    set "key=%%A"
    set "val=%%B"
    set "!key!=!val!"
)

:: 相对路径脚本（保持一致性）
set "AHK_SCRIPT_QUEUE=%BAT_DIR%\ahk\%Queue_Strategy%"
set "AHK_SCRIPT_BTGI=%BAT_DIR%\ahk\change_btgi_window.ahk"
set "AHK_SCRIPT_WAIT=%BAT_DIR%\ahk\wait_until_enter.ahk"
set "AHK_SCRIPT_ENTER=%BAT_DIR%\ahk\enter_door.ahk"
set "AHK_SCRIPT_KONGYUE=%BAT_DIR%\ahk\get_kongyue.ahk"
set "BAT_SEND_LOG=%BAT_DIR%\utils\send_wecom_log.bat"
set "BAT_UPLOAD=%BAT_DIR%\utils\upload_quark.bat"
set "LOG_FILE=%BAT_DIR%\logs\acgi_log.txt"
set "UTF8_LOG=%BAT_DIR%\logs\utf8log.txt"

:: 确保日志目录存在
if not exist "%BTGI_DIR%\log" (
    mkdir "%BTGI_DIR%\log"
)

:: 清空旧日志
del "%LOG_FILE%" >nul 2>&1
:: 如果开启了上传功能，清空screens目录中所有的截图(不删会导致上传失败)
if /i "%Enable_QuarkUpload%"=="true" (
    if exist "%BAT_DIR%\logs\screens\" (
        rmdir /s /q "%BAT_DIR%\logs\screens\"
    )
)

:: 如启用实时风控，则尝试启动 RiskGuard 服务
if /i "%Enable_RiskGuard%"=="true" (
    echo 启动 RiskGuard 服务...
    start "" /min python "%BAT_DIR%utils\risk_guard_service.py"
)

:: 可选操作：开始截图采样
if /i "%Enable_ScreenSampler%"=="true" (
    echo 开始截图采样...
    start "" powershell -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File "%BAT_DIR%utils\screen_sampler.ps1"
    for /f "tokens=2" %%P in ('tasklist /FI "IMAGENAME eq powershell.exe" /FO CSV /NH ^| findstr "screen_sampler.ps1"') do (
        echo %%~P > "%BAT_DIR%sampler.pid"
    )
)

echo [%time%] 启动云游戏... >> "%LOG_FILE%"
start "" "%GI_EXE%"
timeout /t 15 >nul

echo [%time%] 启动排队点击脚本（enter_genshin_queue）... >> "%LOG_FILE%"
start /wait "" "%AHK_EXE%" "%AHK_SCRIPT_QUEUE%"
:: 添加3秒延迟保证已经进入排队界面
timeout /t 3 >nul
:: 等待云游戏排队
start /wait "" "%AHK_EXE%" "%AHK_SCRIPT_WAIT%"
:: 等待游戏启动
timeout /t 60 >nul
:: 进门
start /wait "" "%AHK_EXE%" "%AHK_SCRIPT_ENTER%"
:: 等待进门
timeout /t 40 >nul
:: 摇空月
start /wait "" "%AHK_EXE%" "%AHK_SCRIPT_KONGYUE%"
timeout /t 10 >nul
echo [%time%] 启动 BetterGI 主程序... >> "%LOG_FILE%"
:: 进入 BetterGI 目录再启动
cd /d "%BTGI_DIR%"
start "" "%BTGI_EXE%"
timeout /t 10 >nul

echo [%time%] 执行窗口选中点击脚本（change_btgi_window）... >> "%LOG_FILE%"
start /wait "" "%AHK_EXE%" "%AHK_SCRIPT_BTGI%"
timeout /t 5 >nul

:: 等待 15 分钟用于执行一条龙
timeout /t 900 >nul

echo [%time%] 一条龙执行完毕... >> "%LOG_FILE%"

:: ====== 可选功能：企业微信日志上传 ======
if /i "%Enable_WeComLog%"=="true" (
    echo [%time%] 上传日志到企业微信... >> "%LOG_FILE%"
    call "%BAT_SEND_LOG%"
)

:: === 可选功能：AI日志简报。把当日 LOG 发送到大模型，结果回传企业微信 ===
if /i "%Enable_AI_Summary%"=="true" (
    pwsh -NoProfile -ExecutionPolicy Bypass -File "%BAT_DIR%\utils\bgi_ai_summary.ps1"
    if errorlevel 1 (
        echo [WARN] AI简报发送失败
    ) else (
        echo [OK] AI简报已发送
    )
)

:: 杀掉截图采样
if /i "%Enable_ScreenSampler%"=="true" (
    for /f %%P in (%~dp0sampler.pid) do taskkill /f /pid %%P
    del "%~dp0sampler.pid"
)

:: 上传
if /i "%Enable_QuarkUpload%"=="true" (
    call "%BAT_UPLOAD%"
)
