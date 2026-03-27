CoordMode, Mouse, Screen
CoordMode, Pixel, Screen
#Include %A_ScriptDir%\load_config.ahk

; 封装点击函数（沿用项目风格）
ClickFixed(x, y, clicks := 1) {
    global YOffset
    newY := y + YOffset
    Click, %x%, %newY%, %clicks%
}

; 检测 (1200, 690) 是否有绿色像素点
; 这里搜索 0x00FF00 (BGR 格式，AHK 默认为 BGR) 的近似色
; 1200, 690 是检测点，搜索范围设置在检测点周围小范围内 (±5 像素)
PixelSearch, FoundX, FoundY, ClickPointX_BtgiUpdateGreen-5, ClickPointY_BtgiUpdateGreen-5, ClickPointX_BtgiUpdateGreen+5, ClickPointY_BtgiUpdateGreen+5, 0x00FF00, 50, Fast RGB

if (ErrorLevel = 0) {
    ; 发现绿色像素，判定为更新弹窗
    Sleep, 500
    ClickFixed(ClickPointX_BtgiUpdateIgnore, ClickPointY_BtgiUpdateIgnore) ; 点击“不再提示” (1133, 825)
    Sleep, 1000
}

ExitApp
