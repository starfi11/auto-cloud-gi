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
CoordMode, Mouse, Screen

ClickFixed(x, y, clicks := 1) {
    newY := y + 0
    Click, %x%, %newY%, %clicks%
}
Sleep, 1000                ; 等待 1 秒
; 点击网页端的上传按钮
ClickFixed(ClickPointX_QuarkFileTab, ClickPointY_QuarkFileTab)
Sleep, 2000                ; 等待 2 秒
; 双击指定位置文件（需要预先上传一次对应路径的文件以保证后续打开上传都处在指定文件夹）
ClickFixed(ClickPointX_QuarkTargetDir, ClickPointY_QuarkTargetDir, 2)