if !A_IsAdmin
{
    ; 传递所有命令行参数（若有）
    params := ""
    Loop, %0%
        params .= " """ . %A_Index% . """"

    ; 非编译脚本：用当前 AHK 解释器重启自身
    Run *RunAs "%A_AhkPath%" "%A_ScriptFullPath%" %params%
    ExitApp
}
try DllCall("SetProcessDPIAware")
#Persistent
#Include %A_ScriptDir%\load_config.ahk
SetTitleMatchMode, 2
SetBatchLines, -1
CoordMode, Pixel, Screen
CoordMode, ToolTip, Screen

; 可选：启动稳定等待
if (DelayMs)
    Sleep, %DelayMs%

; ===== 坐标列表（启动时动态获取颜色）=====
pixelPoints := []
pixelPoints.Push({x: 640, y: 480})
pixelPoints.Push({x: 700, y: 500})
; 继续添加：
; pixelPoints.Push({x: 123, y: 456})

; ===== 启动时初始化颜色映射（注意应用 YOffset）=====
Loop % pixelPoints.Length() {
    idx := A_Index
    px  := pixelPoints[idx].x
    py  := pixelPoints[idx].y - YOffset
    PixelGetColor, col, %px%, %py%, RGB
    pixelPoints[idx].color := col
}

; 轮询
SetTimer, CheckPixels, %PollingInterval%
return

CheckPixels:
for idx, point in pixelPoints {
    x := point.x
    y := point.y - YOffset
    base := point.color

    PixelGetColor, now, %x%, %y%, RGB
    if (now != base) {
        ;SoundBeep, 1000, 250
        ;ToolTip, % "✅ 检测成功：(" x "," y ")`n原色：" base " 当前：" now
        SetTimer, CheckPixels, Off
        Sleep, 1200
        ToolTip
        ExitApp
    }
}
;ToolTip, % "🔄 正在轮询像素点中...（共" pixelPoints.Length() "个）"
return
