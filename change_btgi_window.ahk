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
SendMode, Input
SetBatchLines, -1
SetTitleMatchMode, 2
CoordMode, Mouse, Screen

; ---- 可按需修改的常量 ----
DelayMs := 1000                      ; 每次点击后的缓冲
BTGI_WIN := "ahk_exe BetterGI.exe"   ; BTGI 窗口匹配（可换成标题关键字）
SCROLL_TIMES := 80                   ; 兜底滚轮次数
SCROLL_INTERVAL := 5                 ; 每档间隔(ms)
YOffset := 30                        ; 点击Y坐标向下修正的像素量，ECS上偏移就从这里调

ClickFixed(x, y, clicks := 1) {
    global YOffset, DelayMs
    newY := y - YOffset
    Click, %x%, %newY%, %clicks%
    Sleep, %DelayMs%
}


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

; ====== 第二次切到 BTGI（简化版：Alt+Tab 一次） ======
SendInput, {Alt down}{Tab}{Alt up}
Sleep, %DelayMs%

; 7) 点击 579,473（带偏移）
ClickFixed(579, 473)
Sleep, %DelayMs%

; 8) 点击 857,319（带偏移）
ClickFixed(857, 319)


Sleep, %DelayMs%
; 防止没进门 点击 1263,616
ClickFixed(1263, 616)
Sleep, %DelayMs%
; 防止没进门 点击 1263,616
ClickFixed(1263, 616)
Sleep, 10000

ExitApp

