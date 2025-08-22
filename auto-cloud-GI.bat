@echo off
chcp 65001
setlocal enabledelayedexpansion

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
set "AHK_SCRIPT_QUEUE=%BAT_DIR%enter_genshin_queue.ahk"
set "AHK_SCRIPT_BTGI=%BAT_DIR%change_btgi_window.ahk"
set "BAT_SEND_LOG=%BAT_DIR%send_wecom_log.bat"
set "LOG_FILE=%BTGI_DIR%\log\my_log.txt"
set "UTF8_LOG=%BTGI_DIR%\log\utf8log.txt"

:: 确保日志目录存在
if not exist "%BTGI_DIR%\log" (
    mkdir "%BTGI_DIR%\log"
)

:: 清空旧日志
del "%LOG_FILE%" >nul 2>&1

echo [%time%] 启动云原神... >> "%LOG_FILE%"
start "" "%GI_EXE%"
timeout /t 15 >nul

echo [%time%] 启动排队点击脚本（enter_genshin_queue）... >> "%LOG_FILE%"
start "" "%AHK_EXE%" "%AHK_SCRIPT_QUEUE%"

:: 等待 1 分钟用于排队加载和选择原神
timeout /t 60 >nul

echo [%time%] 启动 BetterGI 主程序... >> "%LOG_FILE%"
:: 进入 BetterGI 目录再启动
cd /d "%BTGI_DIR%"
start "" "%BTGI_EXE%"
timeout /t 5 >nul

echo [%time%] 执行窗口选中点击脚本（change_btgi_window）... >> "%LOG_FILE%"
start "" "%AHK_EXE%" "%AHK_SCRIPT_BTGI%"
timeout /t 5 >nul

:: 等待 15 分钟用于执行一条龙
timeout /t 900 >nul

echo [%time%] 一条龙执行完毕，准备上传日志... >> "%LOG_FILE%"

echo [%time%] 上传日志到企业微信... >> "%LOG_FILE%"
call "%BAT_SEND_LOG%"
