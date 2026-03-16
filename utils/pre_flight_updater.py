import os
import sys
import time
import subprocess
import ctypes
import argparse
import pyautogui
from PIL import ImageGrab
import numpy as np
from paddleocr import PaddleOCR
import win32gui
import win32con
import win32api

# 强制开启 DPI 感知，确保坐标计算与物理像素 1:1
try:
    ctypes.windll.shcore.SetProcessDpiAwareness(1)
except Exception:
    ctypes.windll.user32.SetProcessDPIAware()

# 初始化 OCR
# 复用项目中的 PaddleOCR 配置
ocr = PaddleOCR(use_angle_cls=True, lang="ch", show_log=False)

def get_window_rect_accurate(hwnd):
    """
    使用 DwmGetWindowAttribute 获取排除阴影边框后的真实窗口坐标
    """
    rect = ctypes.wintypes.RECT()
    DWMWA_EXTENDED_FRAME_BOUNDS = 9
    ctypes.windll.dwmapi.DwmGetWindowAttribute(
        ctypes.wintypes.HWND(hwnd),
        ctypes.wintypes.DWORD(DWMWA_EXTENDED_FRAME_BOUNDS),
        ctypes.byref(rect),
        ctypes.sizeof(rect)
    )
    return rect.left, rect.top, rect.right, rect.bottom

def find_window_by_title_part(title_part):
    """
    通过部分标题寻找窗口句柄
    """
    found_hwnd = []
    def callback(hwnd, extra):
        if win32gui.IsWindowVisible(hwnd):
            title = win32gui.GetWindowText(hwnd)
            if title_part in title:
                found_hwnd.append(hwnd)
        return True
    win32gui.EnumWindows(callback, None)
    return found_hwnd[0] if found_hwnd else None

def click_text_in_window(hwnd, target_text, offset_x=0, offset_y=0):
    """
    在窗口内寻找文字并点击。返回是否点击成功。
    """
    if not hwnd:
        return False
    
    # 1. 置顶并激活窗口
    win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
    win32gui.SetForegroundWindow(hwnd)
    time.sleep(0.5)

    # 2. 获取精准坐标
    left, top, right, bottom = get_window_rect_accurate(hwnd)
    width, height = right - left, bottom - top

    # 3. 截图
    screenshot = ImageGrab.grab(bbox=(left, top, right, bottom))
    img_array = np.array(screenshot)

    # 4. OCR 识别
    result = ocr.ocr(img_array, cls=True)
    if not result or not result[0]:
        return False

    # 5. 遍历匹配文字
    for line in result[0]:
        text_content = line[1][0]
        if target_text in text_content:
            # 计算文字框的中心点 (相对坐标)
            box = line[0]
            cx = sum([p[0] for p in box]) / 4
            cy = sum([p[1] for p in box]) / 4
            
            # 转换为屏幕绝对坐标
            target_x = left + cx + offset_x
            target_y = top + cy + offset_y
            
            print(f"[DEBUG] 找到目标文本 '{text_content}'，坐标: ({target_x}, {target_y})")
            pyautogui.moveTo(target_x, target_y, duration=0.2)
            pyautogui.click()
            return True
    return False

def check_text_exists(hwnd, keywords):
    """
    检查窗口内是否出现了关键字列表中的任何一个
    """
    if not hwnd:
        return False
    try:
        left, top, right, bottom = get_window_rect_accurate(hwnd)
        screenshot = ImageGrab.grab(bbox=(left, top, right, bottom))
        result = ocr.ocr(np.array(screenshot), cls=True)
        if not result or not result[0]:
            return False
        
        full_text = "".join([line[1][0] for line in result[0]])
        for kw in keywords:
            if kw in full_text:
                return kw
    except Exception as e:
        print(f"[ERROR] check_text_exists 失败: {e}")
    return False

def handle_btgi(exe_path):
    print(f"[*] 启动 BetterGI: {exe_path}")
    subprocess.Popen(exe_path)
    print("[*] 等待 10s 稳定环境...")
    time.sleep(10)
    
    hwnd = find_window_by_title_part("BetterGI")
    if not hwnd:
        print("[!] 未找到 BetterGI 窗口")
        return

    print("[*] 正在扫描更新弹窗...")
    if click_text_in_window(hwnd, "立即更新"):
        print("[+] 已点击立即更新，进入安装监控状态...")
        time.sleep(3)
        
        # 监控安装过程
        max_wait = 300 # 5分钟超时
        start_wait = time.time()
        while time.time() - start_wait < max_wait:
            res = check_text_exists(hwnd, ["更新完成", "安装程序"])
            if res == "更新完成":
                print("[+] 更新完成！准备关闭小窗口...")
                # 用户要求点击右上角的叉。通常这类弹窗很小，我们点文字框右上角外侧
                # 或者直接尝试寻找“确定”/“完成”，如果没有，则点窗口右上角
                # 这里根据用户需求：点击小框右上角的叉
                left, top, right, bottom = get_window_rect_accurate(hwnd)
                # 假设点击小框右上角内部约 20 像素处
                pyautogui.click(right - 20, top + 20)
                print("[+] 已点击叉号关闭")
                break
            time.sleep(5)
        
        # 确保进程关闭 (BTGI 更新完通常会自己退出或者开着个空壳)
        os.system("taskkill /f /im BetterGI.exe >nul 2>&1")
    else:
        print("[*] 未发现更新，正常启动中 (将直接关闭以配合主流程)")
        os.system("taskkill /f /im BetterGI.exe >nul 2>&1")

def handle_genshin(exe_path):
    print(f"[*] 启动 云原神: {exe_path}")
    subprocess.Popen(exe_path)
    print("[*] 等待 10s 稳定环境...")
    time.sleep(10)

    hwnd = find_window_by_title_part("云原神")
    if not hwnd:
        print("[!] 未找到 云原神 窗口")
        return

    print("[*] 正在扫描更新弹窗...")
    if click_text_in_window(hwnd, "立即更新"):
        print("[+] 已点击立即更新，进入进度条等待...")
        time.sleep(3)
        
        # 监控更新成功信号
        max_wait = 1800 # 云游戏更新可能很久，给30分钟
        start_wait = time.time()
        while time.time() - start_wait < max_wait:
            # 重新获取句柄（更新中窗口可能会变）
            hwnd_new = find_window_by_title_part("云原神")
            res = check_text_exists(hwnd_new, ["每日奖励", "开始游戏"])
            if res:
                print(f"[+] 识别到关键信号 '{res}'，更新圆满完成！")
                break
            time.sleep(10)
        
        print("[*] 正在杀掉云原神进程以结束预检...")
        os.system("taskkill /f /im \"Genshin Impact Cloud Game.exe\" >nul 2>&1")
    else:
        print("[*] 未发现更新，直接关闭程序...")
        os.system("taskkill /f /im \"Genshin Impact Cloud Game.exe\" >nul 2>&1")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--app", choices=["btgi", "genshin"], required=True)
    parser.add_argument("--path", required=True)
    args = parser.parse_args()

    if args.app == "btgi":
        handle_btgi(args.path)
    elif args.app == "genshin":
        handle_genshin(args.path)
