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
CoordMode, Mouse, Screen
#Include %A_ScriptDir%\load_config.ahk

ClickFixed(x, y, clicks := 1) {
    global YOffset
    newY := y + YOffset
    Click, %x%, %newY%, %clicks%
}

; ===== 点击逻辑 =====
ClickFixed(ClickPointX_ClaimGift, ClickPointY_ClaimGift)   ; 领取每日赠送时长
Sleep, 2000
ClickFixed(ClickPointX_ClaimGift, ClickPointY_ClaimGift)   ; 领取每日赠送时长
Sleep, 2000
ClickFixed(ClickPointX_StartGame, ClickPointY_StartGame)   ; 点击“开始游戏”
Sleep, 5000

ClickFixed(ClickPointX_QueueNormal, ClickPointY_QueueNormal)   ; 点击“普通队列”

ExitApp
