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

; ===== 进门脚本逻辑 =====

ClickFixed(ClickPointX_DoorEnter, ClickPointY_DoorEnter)
Sleep, 1000

ClickFixed(ClickPointX_DoorEnter, ClickPointY_DoorEnter)
Sleep, 1000

ClickFixed(ClickPointX_DoorEnter, ClickPointY_DoorEnter)
Sleep, 1000

ExitApp
