CoordMode, Mouse, Screen
#Include %A_ScriptDir%\load_config.ahk

ClickFixed(x, y, clicks := 1) {
    global YOffset
    newY := y + YOffset
    Click, %x%, %newY%, %clicks%
}

; ===== 摇空月祝福脚本逻辑 =====

ClickFixed(1539, 1011, 2)
Sleep, 3000
ClickFixed(1539, 1011, 2)
Sleep, 3000
ClickFixed(1676, 1039, 2)
Sleep, 5000
ClickFixed(1676, 1039, 2)
Sleep, 5000
ClickFixed(1538, 1502, 2)
ExitApp
