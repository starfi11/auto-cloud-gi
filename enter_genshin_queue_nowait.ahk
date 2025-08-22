CoordMode, Mouse, Screen
#Include %A_ScriptDir%\load_config.ahk

ClickFixed(x, y, clicks := 1) {
    global YOffset
    newY := y + YOffset
    Click, %x%, %newY%, %clicks%
}

; ===== 点击逻辑 =====

ClickFixed(1395, 843)  ; 点击“开始游戏”
Sleep, 1000

ExitApp
