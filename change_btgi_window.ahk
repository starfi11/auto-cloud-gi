; 该AHK脚本负责在云原神启动后启动bettergi，并模拟点击在bettergi中将捕获窗口手动设置为云原神窗口。
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

Sleep, %DelayMs%
; 防止没进门 点击 1263,616
ClickFixed(1263, 616)
Sleep, %DelayMs%
; 防止没进门 点击
ClickFixed(1263, 781)
Sleep, 10000
Sleep, %DelayMs%
; 防止没进门 点击
ClickFixed(1263, 781)
Sleep, %DelayMs%
; 防止没进门 点击
ClickFixed(1263, 781)

; 0) 先聚焦到 BTGI
if (BTGI_WIN != "") {
    WinActivate, %BTGI_WIN%
    WinWaitActive, %BTGI_WIN%,, 3
}
Sleep, %DelayMs%

; 1) 点击 1130,825
ClickFixed(1130, 825)

; 2) 点击 1345,554
ClickFixed(1345, 554)

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

; 4) 点击 1263,616
ClickFixed(1263, 616)

; 5) 双击 716,477（BTGI 选中原神并把焦点放回原神）
ClickFixed(716, 477, 2)

Sleep, %DelayMs%

; 第二次切换到bettergi界面
Send, {Alt down}{Tab}{Alt up}
Sleep, %DelayMs%

; 7) 点击 579,473（带偏移）
ClickFixed(579, 473)
Sleep, %DelayMs%

; 8) 点击 857,319（带偏移）
ClickFixed(857, 319)

ExitApp

