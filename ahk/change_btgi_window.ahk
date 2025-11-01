; 该AHK脚本负责在云游戏启动后启动bettergi，并模拟点击在bettergi中将捕获窗口手动设置为云游戏窗口。
; 随后再模拟点击启动bettergi一条龙，最后模拟点击避免出现卡在进入游戏界面的情况。
; --- 自提权（以管理员身份重启脚本）---
if !A_IsAdmin
{
    ; 传递所有命令行参数（若有）
    params := ""
    Loop, %0%
        params .= " """ . %A_Index% . """"

    ; 非编译脚本：用当前 AHK 解释器重启自身
    Run *RunAs "%A_AhkPath%" "%A_ScriptFullPath%" %params%
    ExitApp
}
try DllCall("SetProcessDPIAware")

#NoEnv
#SingleInstance Force
#Include %A_ScriptDir%\load_config.ahk

SendMode, Event
SetBatchLines, -1
SetTitleMatchMode, 2
CoordMode, Mouse, Screen

ClickFixed(x, y, clicks := 1) {
    global YOffset, DelayMs
    newY := y + YOffset
    Click, %x%, %newY%, %clicks%
    Sleep, %DelayMs%
}

; 0) 先聚焦到 BTGI
if (BTGI_WIN != "") {
    WinActivate, %BTGI_WIN%
    WinWaitActive, %BTGI_WIN%,, 3
}
Sleep, %DelayMs%

; 1)
; 已废弃操作（无副作用的点击取消更新） 
; ClickFixed(ClickPointX_BtgiOpenCaptureMenu, ClickPointY_BtgiOpenCaptureMenu)

; 2) 展开捕获菜单
ClickFixed(ClickPointX_BtgiExpandList, ClickPointY_BtgiExpandList)

; 3) 下滑到底（End、Ctrl+End + 滚轮兜底）
Send, {End}
Sleep, 50
Send, ^{End}
Sleep, 50
Loop, %SCROLL_TIMES% {
    SendEvent, {WheelDown}
    Sleep, %SCROLL_INTERVAL%
}
Sleep, %DelayMs%

; 4) 选择捕获窗口
ClickFixed(ClickPointX_BtgiPickListItem, ClickPointY_BtgiPickListItem)

; 5) 双击 716,477（BTGI 选中游戏并把焦点放回游戏）
ClickFixed(ClickPointX_BtgiFocusGame, ClickPointY_BtgiFocusGame, 2)

Sleep, %DelayMs%
Sleep, 10000
; 第二次切换到bettergi界面
Send, {Alt down}{Tab}{Alt up}
Sleep, %DelayMs%

; 7) 切换到左侧栏的一条龙
ClickFixed(ClickPointX_BtgiStartDragon1, ClickPointY_BtgiStartDragon1)
Sleep, %DelayMs%

; 8) 启动一条龙
ClickFixed(ClickPointX_BtgiStartDragon2, ClickPointY_BtgiStartDragon2)

ExitApp

