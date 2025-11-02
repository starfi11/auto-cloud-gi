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
