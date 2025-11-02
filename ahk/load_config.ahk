; ================= load_config.ahk =================
; 目标：一次性加载 config.ini 中所有键为同名全局变量，
;      并保持原脚本“读取后的效果不变”（含必要的默认值）

; === 统一读取 config.ini（从项目根目录）===
configFile := A_ScriptDir . "\..\config.ini"
LoadIniAll(configFile)  ; 加载所有 section 的 key=value

; === 兼容旧逻辑的默认值 ===
if (BTGI_WIN = "")
    BTGI_WIN := "ahk_exe BetterGI.exe"
if (SCROLL_TIMES = "")
    SCROLL_TIMES := 80
if (SCROLL_INTERVAL = "")
    SCROLL_INTERVAL := 5
if (PollingInterval = "")
    PollingInterval := 3000

; ------------------------------------------------------------
; LoadIniAll(file)
; 作用：把 INI 文件中所有 section 的所有 key=value 读取为同名全局变量。
; 规则：
;   - 跳过空行、以 ';' 开头的注释行、以及 [Section] 标题行
;   - 仅按第一个 '=' 分割 key 与 value
;   - key/value 两端会 Trim 空白
;   - 若不同 section 存在同名 key，后出现者覆盖先前值
; ------------------------------------------------------------
LoadIniAll(file) {
    global
    if !FileExist(file) {
        MsgBox, 16, config.ini not found, 未找到配置文件：%file%
        return false
    }
    Loop, Read, %file%
    {
        line := Trim(A_LoopReadLine)
        if (line = "" || SubStr(line, 1, 1) = ";")
            continue
        if (SubStr(line, 1, 1) = "[" && SubStr(line, 0) = "]")
            continue  ; 跳过 [Section] 标题

        pos := InStr(line, "=")
        if (!pos)
            continue

        key := RTrim(SubStr(line, 1, pos - 1))
        val := LTrim(SubStr(line, pos + 1))

        ; —— 去除值后的行尾注释 ——
        cpos := InStr(val, ";")
        if (cpos)  val := RTrim(SubStr(val, 1, cpos - 1))

        ; 动态创建同名全局变量
        %key% := val
    }
    return true
}
