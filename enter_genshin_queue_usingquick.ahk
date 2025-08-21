CoordMode, Mouse, Screen

; ---- 垂直偏移设置 ----
YOffset := 30  ; ECS上向下偏移的问题从这里统一调整

ClickFixed(x, y, clicks := 1) {
    global YOffset
    newY := y - YOffset
    Click, %x%, %newY%, %clicks%
}

; ===== 点击逻辑 =====

ClickFixed(1395, 843)  ; 点击“开始游戏”
Sleep, 5000

ClickFixed(872, 507)   ; 点击“优先队列”

ExitApp
