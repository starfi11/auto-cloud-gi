param(
    [string]$OutRoot = "C:\ProgramData\auto-cloud-GI\screens",
    [int]$IntervalSec = 10
)

# 尽量安静运行
$ErrorActionPreference = "Stop"

# 准备依赖：GDI+ / WinForms
Add-Type -AssemblyName System.Drawing
Add-Type -AssemblyName System.Windows.Forms

# 创建当天目录：YYYYMMDD
function Get-DayDir {
    $day = (Get-Date).ToString("yyyyMMdd")
    $dir = Join-Path $OutRoot $day
    if (!(Test-Path $dir)) { New-Item -ItemType Directory -Path $dir | Out-Null }
    return $dir
}

# 获取虚拟屏
function Get-VirtualBounds {
    $vs = [System.Windows.Forms.SystemInformation]::VirtualScreen
    return @{
        X = $vs.X; Y = $vs.Y; W = $vs.Width; H = $vs.Height
    }
}

# 截图一次并保存为 PNG
function Capture-Once {
    $bounds = Get-VirtualBounds
    if ($bounds.W -le 0 -or $bounds.H -le 0) { return }

    $bmp = New-Object System.Drawing.Bitmap($bounds.W, $bounds.H, [System.Drawing.Imaging.PixelFormat]::Format32bppArgb)
    $gfx = [System.Drawing.Graphics]::FromImage($bmp)
    try {
        $gfx.CopyFromScreen($bounds.X, $bounds.Y, 0, 0, $bmp.Size)
        $dir = Get-DayDir
        $name = (Get-Date).ToString("HHmmss.fff") + ".png"
        $path = Join-Path $dir $name

        $codec = [System.Drawing.Imaging.ImageCodecInfo]::GetImageEncoders() | Where-Object { $_.MimeType -eq "image/png" }
        $encParams = New-Object System.Drawing.Imaging.EncoderParameters(1)
        $encParams.Param[0] = New-Object System.Drawing.Imaging.EncoderParameter([System.Drawing.Imaging.Encoder]::Quality, 100L)
        if ($codec) { $bmp.Save($path, $codec, $encParams) } else { $bmp.Save($path, [System.Drawing.Imaging.ImageFormat]::Png) }
    }
    finally {
        $gfx.Dispose()
        $bmp.Dispose()
    }
}

# 轮询采样
while ($true) {
    try { Capture-Once } catch { }
    Start-Sleep -Seconds $IntervalSec
}
