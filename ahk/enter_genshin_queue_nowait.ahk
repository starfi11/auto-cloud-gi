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
Sleep, 1000

ExitApp
