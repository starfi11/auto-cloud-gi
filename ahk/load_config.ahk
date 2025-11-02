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
; ===== ClickPoints（通用进入）=====
IniRead, ClickPointX_ClaimGift, %configFile%, ClickPoints, ClickPointX_ClaimGift
IniRead, ClickPointY_ClaimGift, %configFile%, ClickPoints, ClickPointY_ClaimGift
IniRead, ClickPointX_StartGame,  %configFile%, ClickPoints, ClickPointX_StartGame
IniRead, ClickPointY_StartGame,  %configFile%, ClickPoints, ClickPointY_StartGame
IniRead, ClickPointX_QueueNormal,%configFile%, ClickPoints, ClickPointX_QueueNormal
IniRead, ClickPointY_QueueNormal,%configFile%, ClickPoints, ClickPointY_QueueNormal
IniRead, ClickPointX_QueueQuick, %configFile%, ClickPoints, ClickPointX_QueueQuick
IniRead, ClickPointY_QueueQuick, %configFile%, ClickPoints, ClickPointY_QueueQuick
IniRead, ClickPointX_DoorEnter,  %configFile%, ClickPoints, ClickPointX_DoorEnter
IniRead, ClickPointY_DoorEnter,  %configFile%, ClickPoints, ClickPointY_DoorEnter

; ===== ClickPoints（BetterGI）=====
IniRead, ClickPointX_BtgiExpandList,  %configFile%, ClickPoints, ClickPointX_BtgiExpandList
IniRead, ClickPointY_BtgiExpandList,  %configFile%, ClickPoints, ClickPointY_BtgiExpandList
IniRead, ClickPointX_BtgiPickListItem,%configFile%, ClickPoints, ClickPointX_BtgiPickListItem
IniRead, ClickPointY_BtgiPickListItem,%configFile%, ClickPoints, ClickPointY_BtgiPickListItem
IniRead, ClickPointX_BtgiFocusGame,   %configFile%, ClickPoints, ClickPointX_BtgiFocusGame
IniRead, ClickPointY_BtgiFocusGame,   %configFile%, ClickPoints, ClickPointY_BtgiFocusGame
IniRead, ClickPointX_BtgiStartDragon1,%configFile%, ClickPoints, ClickPointX_BtgiStartDragon1
IniRead, ClickPointY_BtgiStartDragon1,%configFile%, ClickPoints, ClickPointY_BtgiStartDragon1
IniRead, ClickPointX_BtgiStartDragon2,%configFile%, ClickPoints, ClickPointX_BtgiStartDragon2
IniRead, ClickPointY_BtgiStartDragon2,%configFile%, ClickPoints, ClickPointY_BtgiStartDragon2

; ===== ClickPoints（空月）=====
IniRead, ClickPointX_KongyueA, %configFile%, ClickPoints, ClickPointX_KongyueA
IniRead, ClickPointY_KongyueA, %configFile%, ClickPoints, ClickPointY_KongyueA
IniRead, ClickPointX_KongyueB, %configFile%, ClickPoints, ClickPointX_KongyueB
IniRead, ClickPointY_KongyueB, %configFile%, ClickPoints, ClickPointY_KongyueB
IniRead, ClickPointX_KongyueC, %configFile%, ClickPoints, ClickPointX_KongyueC
IniRead, ClickPointY_KongyueC, %configFile%, ClickPoints, ClickPointY_KongyueC

; ===== ClickPoints（夸克上传）=====
IniRead, ClickPointX_QuarkFileTab,   %configFile%, ClickPoints, ClickPointX_QuarkFileTab
IniRead, ClickPointY_QuarkFileTab,   %configFile%, ClickPoints, ClickPointY_QuarkFileTab
IniRead, ClickPointX_QuarkTargetDir, %configFile%, ClickPoints, ClickPointX_QuarkTargetDir
IniRead, ClickPointY_QuarkTargetDir, %configFile%, ClickPoints, ClickPointY_QuarkTargetDir