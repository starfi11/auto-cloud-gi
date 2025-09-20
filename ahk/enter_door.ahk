CoordMode, Mouse, Screen
#Include %A_ScriptDir%\load_config.ahk

ClickFixed(x, y, clicks := 1) {
    global YOffset
    newY := y + YOffset
    Click, %x%, %newY%, %clicks%
}

; ===== 进门脚本逻辑 =====

ClickFixed(960, 1005)
Sleep, 1000

ClickFixed(960, 1005)
Sleep, 1000

ClickFixed(960, 1005)
Sleep, 1000

ExitApp
