CoordMode, Mouse, Screen
#Include %A_ScriptDir%\load_config.ahk

ClickFixed(x, y, clicks := 1) {
    global YOffset
    newY := y + YOffset
    Click, %x%, %newY%, %clicks%
}

; ===== 摇空月祝福脚本逻辑 =====

ClickFixed(ClickPointX_KongyueA, ClickPointY_KongyueA, 2)
Sleep, 3000
ClickFixed(ClickPointX_KongyueA, ClickPointY_KongyueA, 2)
Sleep, 3000
ClickFixed(ClickPointX_KongyueB, ClickPointY_KongyueB, 2)
Sleep, 5000
ClickFixed(ClickPointX_KongyueB, ClickPointY_KongyueB, 2)
Sleep, 5000
ClickFixed(ClickPointX_KongyueC, ClickPointY_KongyueC, 2)
ExitApp
