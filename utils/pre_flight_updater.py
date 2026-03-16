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

# 强制开启 DPI 感知，确保坐标计算与物理像素 1:1
try:
    ctypes.windll.shcore.SetProcessDpiAwareness(1)
except Exception:
    ctypes.windll.user32.SetProcessDPIAware()

# 初始化 OCR
# 兼容不同版本的 PaddleOCR 参数
try:
    ocr = PaddleOCR(use_textline_orientation=True, lang="ch")
except Exception:
    ocr = PaddleOCR(use_angle_cls=True, lang="ch")

def click_text_on_screen(target_text, offset_x=0, offset_y=0):
    """
    在全屏寻找文字并点击。返回是否点击成功。
    """
    screenshot = ImageGrab.grab()
    img_array = np.array(screenshot)

    # 4. OCR 识别
    result = ocr.ocr(img_array, cls=True)
    if not result or not result[0]:
        return False

    # 5. 遍历匹配文字
    for line in result[0]:
        text_content = line[1][0]
        if target_text in text_content:
            box = line[0]
            cx = sum([p[0] for p in box]) / 4
            cy = sum([p[1] for p in box]) / 4
            
            target_x = cx + offset_x
            target_y = cy + offset_y
            
            print(f"[DEBUG] 找到目标文本 '{text_content}'，全屏坐标: ({target_x}, {target_y})")
            pyautogui.moveTo(target_x, target_y, duration=0.2)
            pyautogui.click()
            return True
    return False

def check_text_exists_on_screen(keywords):
    """
    检查全屏是否出现了关键字列表中的任何一个
    """
    try:
        screenshot = ImageGrab.grab()
        result = ocr.ocr(np.array(screenshot), cls=True)
        if not result or not result[0]:
            return False
        
        full_text = "".join([line[1][0] for line in result[0]])
        for kw in keywords:
            if kw in full_text:
                return kw
    except Exception as e:
        print(f"[ERROR] check_text_exists_on_screen 失败: {e}")
    return False

def handle_btgi(exe_path):
    print(f"[*] 启动 BetterGI: {exe_path}")
    subprocess.Popen(exe_path)
    print("[*] 等待 10s 稳定环境...")
    time.sleep(10)
    
    print("[*] 正在全屏扫描更新弹窗...")
    if click_text_on_screen("立即更新"):
        print("[+] 已点击立即更新，进入安装监控状态...")
        time.sleep(3)
        
        # 监控安装过程
        max_wait = 300 # 5分钟超时
        start_wait = time.time()
        while time.time() - start_wait < max_wait:
            res = check_text_exists_on_screen(["更新完成", "安装程序"])
            if res == "更新完成":
                print("[+] 更新完成！准备结束流程...")
                break
            time.sleep(5)
            
    else:
        print("[*] 未发现更新，正常启动中...")

    print("[*] 确保清理相关进程...")
    os.system("taskkill /f /im BetterGI.exe >nul 2>&1")
    # 为了防止一些带 Updater 的残留进程，可选地静默杀掉可能的同名进程
    os.system("taskkill /f /im BetterGI*.exe >nul 2>&1")
    time.sleep(5)

def handle_genshin(exe_path):
    print(f"[*] 启动 云原神: {exe_path}")
    subprocess.Popen(exe_path)
    print("[*] 等待 10s 稳定环境...")
    time.sleep(10)

    print("[*] 正在全屏扫描更新弹窗...")
    if click_text_on_screen("立即更新"):
        print("[+] 已点击立即更新，进入进度条等待...")
        time.sleep(3)
        
        # 监控更新成功信号
        max_wait = 600 # 云游戏更新时间最多给到10分钟
        start_wait = time.time()
        while time.time() - start_wait < max_wait:
            res = check_text_exists_on_screen(["每日奖励", "开始游戏"])
            if res:
                print(f"[+] 识别到关键信号 '{res}'，更新圆满完成！")
                break
            time.sleep(10)
    else:
        print("[*] 未发现更新，直接进入关闭流程...")

    print("[*] 确保清理相关进程...")
    os.system("taskkill /f /im \"Genshin Impact Cloud Game.exe\" >nul 2>&1")
    time.sleep(5)

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--app", choices=["btgi", "genshin"], required=True)
    parser.add_argument("--path", required=True)
    args = parser.parse_args()

    if args.app == "btgi":
        handle_btgi(args.path)
    elif args.app == "genshin":
        handle_genshin(args.path)
