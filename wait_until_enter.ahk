#Persistent
#Include %A_ScriptDir%\load_config.ahk
SetTitleMatchMode, 2
SetBatchLines, -1
CoordMode, Pixel, Screen
CoordMode, ToolTip, Screen

; ===== 只提供坐标列表（颜色将在脚本启动时动态获取） =====
pixelPoints := [
    {x: 640, y: 480},
    {x: 700, y: 500}
    ; 可继续添加更多点
]

; ===== 启动时初始化颜色映射（注意应用 YOffset） =====
Loop % pixelPoints.Length() {
    index := A_Index
    px := pixelPoints[index].x
    py := pixelPoints[index].y - YOffset
    PixelGetColor, col, %px%, %py%, RGB
    pixelPoints[index].color := col
}

SetTimer, CheckPixels, %PollingInterval%
return

CheckPixels:
for index, point in pixelPoints {
    x := point.x
    y := point.y - YOffset  
    base := point.color

    PixelGetColor, now, %x%, %y%, RGB
    if (now != base) {
        ToolTip, 检测成功：(%x%,%y%)\n原色：%base% 当前：%now%
        SetTimer, CheckPixels, Off
        Sleep, 2000
        ToolTip
        ExitApp
    }
}
ToolTip, 正在轮询像素点中...（共%pixelPoints.Length()%个）
return
