CoordMode, Mouse, Screen

ClickFixed(x, y, clicks := 1) {
    newY := y + 0
    Click, %x%, %newY%, %clicks%
}
Sleep, 1000                ; 等待 1 秒
ClickFixed(302, 182)       ; 单击 (302,182)
Sleep, 2000                ; 等待 2 秒
ClickFixed(218, 185, 2)    ; 双击 (218,185)