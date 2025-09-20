@echo off
chcp 65001
setlocal enabledelayedexpansion

:: ========== 读取 config.ini ==========
set "BAT_DIR=%~dp0"
set "ROOT_DIR=%BAT_DIR%.."
set "CONFIG_FILE=%ROOT_DIR%\config.ini"
if not exist "%CONFIG_FILE%" (
  echo 配置文件不存在: "%CONFIG_FILE%"
  exit /b 1
)

for /f "tokens=1,* delims==" %%A in ('findstr "=" "%CONFIG_FILE%"') do (
  set "key=%%A"
  set "val=%%B"
  set "!key!=!val!"
)

for /f %%i in ('powershell -NoProfile -Command "Get-Date -Format yyyyMMdd"') do set "TODAY=%%i"
set "LOG_FILE=%LOG_DIR%\better-genshin-impact%TODAY%.log"

:: 检查文件是否存在
if not exist "%LOG_FILE%" (
    echo 找不到日志文件: %LOG_FILE%
    exit /b 1
)

echo 找到日志文件: %LOG_FILE%

:: 上传文件，获取 media_id
echo 正在上传文件至企业微信...

curl -s -X POST "https://qyapi.weixin.qq.com/cgi-bin/webhook/upload_media?key=%HOOK_KEY%&type=file" ^
  -H "Content-Type: multipart/form-data" ^
  -F "media=@%LOG_FILE%;type=application/octet-stream" > upload_result.json

:: 提取 media_id
for /f "delims=" %%a in ('powershell -NoProfile -Command ^
  "(Get-Content -Raw 'upload_result.json' | ConvertFrom-Json).media_id"') do set "MEDIA_ID=%%a"

echo 提取的 media_id: [%MEDIA_ID%]

if not defined MEDIA_ID (
    echo 未能提取 media_id，请检查 upload_result.json 内容：
    type upload_result.json
    exit /b 1
)

echo 上传成功，media_id: %MEDIA_ID%

:: 构造发送请求
(
echo {
echo   "msgtype": "file",
echo   "file": {
echo     "media_id": "%MEDIA_ID%"
echo   }
echo }
) > body.json

:: 发送文件消息
echo 正在发送文件消息到微信群...

curl -s -X POST "https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=%HOOK_KEY%" ^
  -H "Content-Type: application/json" ^
  -d @body.json > send_result.json

echo 文件消息发送完成
type send_result.json

:: 清理临时文件
del upload_result.json >nul 2>&1
del body.json >nul 2>&1
