; === 统一读取 config.ini（从项目根目录）===
configFile := A_ScriptDir . "\..\config.ini"

; ===== 路径配置 =====
IniRead, BTGI_DIR, %configFile%, Paths, BTGI_DIR
IniRead, GI_EXE, %configFile%, Paths, GI_EXE
IniRead, HOOK_URL, %configFile%, Paths, HOOK_URL

; ===== AHK 配置 =====
IniRead, YOffset,          %configFile%, AHK, YOffset
IniRead, DelayMs,          %configFile%, AHK, DelayMs
IniRead, BTGI_WIN,         %configFile%, AHK, BTGI_WIN, ahk_exe BetterGI.exe
IniRead, SCROLL_TIMES,     %configFile%, AHK, SCROLL_TIMES, 80
IniRead, SCROLL_INTERVAL,  %configFile%, AHK, SCROLL_INTERVAL, 5
IniRead, PollingInterval,  %configFile%, AHK, PollingInterval, 3000