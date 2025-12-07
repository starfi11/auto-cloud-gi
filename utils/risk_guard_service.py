# utils/risk_guard_service.py
import os
import json
import base64
import queue
import threading
import subprocess
from datetime import datetime

import requests
import cv2
from paddleocr import PaddleOCR
from flask import Flask, request, jsonify
import configparser

# ========== 路径 & 配置 ==========
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT_DIR = os.path.abspath(os.path.join(SCRIPT_DIR, ".."))
CONFIG_PATH = os.path.join(ROOT_DIR, "config.ini")

print("[RiskGuard] SCRIPT_DIR =", SCRIPT_DIR)
print("[RiskGuard] ROOT_DIR   =", ROOT_DIR)
print("[RiskGuard] CONFIG_PATH =", CONFIG_PATH)

cfg = configparser.ConfigParser()
read_files = cfg.read(CONFIG_PATH, encoding="utf-8")
print("[RiskGuard] config read files:", read_files)

# 功能开关（来自 [Features]）
ENABLE_RISK_GUARD = cfg.getboolean("Features", "Enable_RiskGuard", fallback=False)
print("[RiskGuard] ENABLE_RISK_GUARD =", ENABLE_RISK_GUARD)

# 路径信息（来自 [Paths]）
HOOK_URL = cfg.get("Paths", "HOOK_URL", fallback=None)
GI_EXE = os.path.basename(cfg.get("Paths", "GI_EXE", fallback=""))
BTGI_EXE = os.path.basename(cfg.get("Paths", "BTGI_EXE", fallback="BetterGI.exe"))
print("[RiskGuard] HOOK_URL =", HOOK_URL)
print("[RiskGuard] GI_EXE   =", GI_EXE)
print("[RiskGuard] BTGI_EXE =", BTGI_EXE)

# RiskGuard 细节（来自 [RiskGuard]）
QUEUE_MAXSIZE = int(cfg.get("RiskGuard", "QUEUE_MAXSIZE", fallback="100"))
OCR_LANG = cfg.get("RiskGuard", "OCR_LANG", fallback="ch")
CENTER_RATIO = float(cfg.get("RiskGuard", "CENTER_RATIO", fallback="0.7"))
print("[RiskGuard] QUEUE_MAXSIZE =", QUEUE_MAXSIZE)
print("[RiskGuard] OCR_LANG      =", OCR_LANG)
print("[RiskGuard] CENTER_RATIO  =", CENTER_RATIO)

# 通义千问（优先使用 config.ini 的 [DashScope]，没配时再 fallback 到环境变量）
DASHSCOPE_API_KEY = cfg.get(
    "DashScope",
    "DASHSCOPE_API_KEY",
    fallback=os.environ.get("DASHSCOPE_API_KEY", "")
)
DASHSCOPE_BASE_URL = cfg.get(
    "DashScope",
    "DASHSCOPE_BASE_URL",
    fallback=os.environ.get(
        "DASHSCOPE_BASE_URL",
        "https://dashscope.aliyuncs.com/compatible-mode/v1"
    )
)
QWEN_VL_MODEL = cfg.get(
    "DashScope",
    "QWEN_VL_MODEL",
    fallback=os.environ.get("QWEN_VL_MODEL", "qwen3-vl-flash")
)
print("[RiskGuard] DASHSCOPE_BASE_URL =", DASHSCOPE_BASE_URL)
print("[RiskGuard] QWEN_VL_MODEL      =", QWEN_VL_MODEL)
print("[RiskGuard] DASHSCOPE_API_KEY configured:", bool(DASHSCOPE_API_KEY))

# 大模型调用次数限制（可选：从 [RiskGuard] 里配置 MAX_LLM_CALLS，默认 3）
LLM_CALL_LIMIT = int(cfg.get("RiskGuard", "MAX_LLM_CALLS", fallback="3"))
llm_call_count = 0  # 进程级计数器，worker_loop 中使用
print("[RiskGuard] LLM_CALL_LIMIT =", LLM_CALL_LIMIT)

app = Flask(__name__)
task_q: "queue.Queue[str]" = queue.Queue(maxsize=QUEUE_MAXSIZE)

# ========== OCR 初始化（OpenCV + PaddleOCR） ==========
print("[RiskGuard] Initializing PaddleOCR with lang =", OCR_LANG)
ocr_engine = PaddleOCR(
    lang=OCR_LANG,
    use_doc_orientation_classify=False,
    use_doc_unwarping=False,
    use_textline_orientation=True,  # 取代旧的 use_angle_cls
    # device="cpu",  # 可选：想显式写也可以加这行
)
print("[RiskGuard] PaddleOCR initialized.")

def crop_center_region(img_bgr):
    """裁剪屏幕中心 CENTER_RATIO 的区域，img_bgr 是 OpenCV BGR 图像"""
    h, w = img_bgr.shape[:2]
    r = CENTER_RATIO
    x0 = int(w * (1 - r) / 2)
    y0 = int(h * (1 - r) / 2)
    x1 = int(w * (1 + r) / 2)
    y1 = int(h * (1 + r) / 2)
    print(f"[RiskGuard] crop_center_region: w={w}, h={h}, x0={x0}, y0={y0}, x1={x1}, y1={y1}")
    return img_bgr[y0:y1, x0:x1]


def ocr_center_text(img_path: str) -> str:
    """对截图中心区域做 OCR，返回提取的文本（整合成一串）"""
    print(f"[RiskGuard] ocr_center_text: img_path={img_path}")
    img = cv2.imread(img_path)
    if img is None:
        print("[RiskGuard] ocr_center_text: cv2.imread returned None")
        return ""

    print(f"[RiskGuard] ocr_center_text: img shape={img.shape}")
    center = crop_center_region(img)
    print("[RiskGuard] ocr_center_text: center cropped")

    try:
        result = ocr_engine.ocr(center)
    except Exception as e:
        print("[RiskGuard] ocr_center_text: ocr_engine.ocr error:", e)
        return ""

    # 顶层一般是 list；我们先打一下类型
    print(
        "[RiskGuard] ocr_center_text: type(result)=",
        type(result),
        " len=",
        len(result) if result is not None else "None",
    )

    texts: list[str] = []

    if not result:
        print("[RiskGuard] ocr_center_text: result is empty")
        return ""

    first = result[0]
    print("[RiskGuard] ocr_center_text: type(result[0])=", type(first))

    # === 新版 PaddleOCR：result[0] 是 dict，真正的文字在 rec_texts 里 ===
    if isinstance(first, dict):
        rec_texts = first.get("rec_texts") or []
        print(
            "[RiskGuard] ocr_center_text: use dict['rec_texts'], count=",
            len(rec_texts),
        )
        for idx, t in enumerate(rec_texts):
            txt = str(t)
            print(f"[RiskGuard]   rec_texts[{idx}] = {txt!r}")
            texts.append(txt)

    # === 兼容旧格式：result[0] 是 list，每一项是 [box, (text, score)] 或类似结构 ===
    elif isinstance(first, (list, tuple)):
        print("[RiskGuard] ocr_center_text: use legacy list format, len(result[0])=", len(first))
        for idx, line in enumerate(first):
            print(f"[RiskGuard]   raw line[{idx}] = {line!r}")
            if not isinstance(line, (list, tuple)) or len(line) < 2:
                continue
            text_field = line[1]
            # 可能是 ('文本', score) / ['文本', score] / 直接就是 '文本'
            if isinstance(text_field, (list, tuple)):
                txt = str(text_field[0])
            else:
                txt = str(text_field)
            print(f"[RiskGuard]   parsed text[{idx}] = {txt!r}")
            texts.append(txt)

    else:
        # 完全未知的格式，打印出来看
        print("[RiskGuard] ocr_center_text: unknown format for result[0] =", first)

    joined = "".join(texts)
    print(f"[RiskGuard] ocr_center_text: joined_text={joined!r}")
    return joined


# 风险关键词
RISK_KEYWORDS = [
    "封禁", "封停", "封号", "风控",
    "外挂", "脚本", "第三方工具",
    "限制登录", "异常登录", "安全风险",
    "封号1天", "封号三天", "封号7天", "封号30天",
]
print("[RiskGuard] RISK_KEYWORDS =", RISK_KEYWORDS)


def has_risk_keyword(text: str) -> bool:
    hit = any(k in text for k in RISK_KEYWORDS)
    print(f"[RiskGuard] has_risk_keyword: text='{text}', hit={hit}")
    return hit


# ========== 通义千问多模态模型 ==========
def call_vision_llm(img_path: str, ocr_text: str) -> tuple[bool, str]:
    """
    调用通义千问 Qwen-VL 对风险弹窗做判断 + 简短解释。

    返回:
        (is_risky, comment)
        - is_risky: True 表示确认为风险，需要杀进程 + 告警
        - comment: 30 字左右的中文解释
    """
    print(f"[RiskGuard] call_vision_llm: img_path={img_path}")
    print(f"[RiskGuard] call_vision_llm: ocr_text='{ocr_text}'")
    if not DASHSCOPE_API_KEY:
        print("[RiskGuard] call_vision_llm: no DASHSCOPE_API_KEY, skip model.")
        return False, "未配置 DASHSCOPE_API_KEY，跳过模型分析。"

    try:
        with open(img_path, "rb") as f:
            img_bytes = f.read()
        print(f"[RiskGuard] call_vision_llm: image bytes length={len(img_bytes)}")
        b64 = base64.b64encode(img_bytes).decode("ascii")
    except Exception as e:
        print("[RiskGuard] call_vision_llm: failed to read/encode image:", e)
        return False, f"读取图片失败：{e}"

    # 让模型输出一个非常严格格式的 JSON，方便解析：
    # {"risk": true, "comment": "xxx"}
    prompt_text = f"""你是原神云游戏的风控助手。

这是一张游戏或云游戏平台的截图，中心区域包含提示框。
已经通过 OCR 识别出如下文字：

{ocr_text}

请你判断是否与 封号、封禁、封停、风控、
检测到外挂/脚本、账号安全、限制登录 等风险有关。

你必须按照如下规则输出（非常重要）：
1. 严格输出单行 JSON 字符串，不要有多余文字，例如：
   {{"risk": true, "comment": "检测到非法脚本，账号封禁1天"}}
2. 当你判断存在上述风险时，risk 为 true；
   当你判断「没有明显风险」时，risk 为 false。
3. comment 必须是 不超过30个汉字 的中文解释。
4. 不要输出任何其它说明文字，不要换行，不要加反引号。
"""

    body = {
        "model": QWEN_VL_MODEL,
        "messages": [
            {
                "role": "system",
                "content": "你是一个严谨的风控告警助手，只用 JSON 给出结论。",
            },
            {
                "role": "user",
                "content": [
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:image/png;base64,{b64}"
                        },
                    },
                    {"type": "text", "text": prompt_text},
                ],
            },
        ],
    }

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {DASHSCOPE_API_KEY}",
    }

    print("[RiskGuard] call_vision_llm: sending request to DashScope...")
    try:
        resp = requests.post(
            f"{DASHSCOPE_BASE_URL}/chat/completions",
            headers=headers,
            data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
            timeout=15,
        )
        print("[RiskGuard] call_vision_llm: resp.status_code =", resp.status_code)
        # 避免太长，这里只打印前几百字符
        raw_json = resp.text
        print("[RiskGuard] call_vision_llm: resp.text (truncated) =", raw_json[:500])
        data = resp.json()
        content = data["choices"][0]["message"]["content"]
        print("[RiskGuard] call_vision_llm: content type =", type(content))
        print("[RiskGuard] call_vision_llm: content (raw) =", content)
        # 兼容 string / list 两种情况
        if isinstance(content, str):
            raw = content.strip()
        elif isinstance(content, list):
            texts = [
                item.get("text", "")
                for item in content
                if isinstance(item, dict) and item.get("type") == "text"
            ]
            raw = "".join(texts).strip()
        else:
            print("[RiskGuard] call_vision_llm: unknown content type, treat as no risk.")
            return False, "模型返回内容格式未知。"

        print("[RiskGuard] call_vision_llm: raw after normalize =", raw)

        # 尝试解析 JSON
        try:
            obj = json.loads(raw)
            print("[RiskGuard] call_vision_llm: parsed JSON =", obj)
            is_risky = bool(obj.get("risk", False))
            comment = str(obj.get("comment", "")).strip() or raw
            print(f"[RiskGuard] call_vision_llm: is_risky={is_risky}, comment='{comment}'")
            return is_risky, comment
        except Exception as e:
            print("[RiskGuard] call_vision_llm: json.loads failed, fallback:", e)
            # 兜底：解析失败时，用简单规则判断
            safe_phrases = [
                "未检测到明显封禁提示",
                "未检测到封禁",
                "未检测到明显风险",
                "无明显封禁",
                "没有明显风险",
            ]
            is_risky = not any(p in raw for p in safe_phrases)
            comment = raw or "模型返回内容无法解析，默认视为无风险。"
            print(f"[RiskGuard] call_vision_llm: fallback is_risky={is_risky}, comment='{comment}'")
            return is_risky, comment

    except Exception as e:
        # 请求失败统一视为「无法判断 / 不告警」
        print("[RiskGuard] call_vision_llm: request error:", e)
        return False, f"模型调用失败：{e}"


# ========== 杀进程 & 企业微信告警 ==========
def kill_gi_and_btgi():
    print("[RiskGuard] kill_gi_and_btgi: GI_EXE=", GI_EXE, "BTGI_EXE=", BTGI_EXE)
    for exe in (GI_EXE, BTGI_EXE):
        if not exe:
            print("[RiskGuard] kill_gi_and_btgi: skip empty exe name")
            continue
        try:
            print(f"[RiskGuard] kill_gi_and_btgi: try kill {exe}")
            subprocess.run(
                ["taskkill", "/f", "/im", exe],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=False,
            )
        except Exception as e:
            print(f"[RiskGuard] kill {exe} failed: {e}")


def send_wecom_alert(ocr_text: str, llm_comment: str, img_path: str):
    print("[RiskGuard] send_wecom_alert called.")
    if not HOOK_URL:
        print("[RiskGuard] HOOK_URL 未配置，跳过企微告警。")
        return
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    content = (
        f"【⚠ 原神风控告警】\n"
        f"> 时间：{ts}\n"
        f"> OCR 文本：{ocr_text}\n"
        f"> 模型点评：{llm_comment}\n"
        f"> 截图路径：{img_path}\n"
        f"> 处置：已尝试自动结束云原神与 BetterGI 进程，请人工确认。\n"
    )
    print("[RiskGuard] send_wecom_alert: content=\n", content)
    payload = {"msgtype": "text", "text": {"content": content}}
    try:
        r = requests.post(HOOK_URL, json=payload, timeout=5)
        print("[RiskGuard] wecom resp:", r.status_code, r.text[:200])
    except Exception as e:
        print("[RiskGuard] send wecom failed:", e)


# ========== Worker ==========
def worker_loop():
    global llm_call_count
    print("[RiskGuard] worker started, Enable_RiskGuard =", ENABLE_RISK_GUARD)
    print(f"[RiskGuard] LLM_CALL_LIMIT = {LLM_CALL_LIMIT}")
    while True:
        img_path = task_q.get()
        print("[RiskGuard] worker_loop: got task img_path =", img_path)
        try:
            if not ENABLE_RISK_GUARD:
                # 开关关闭时，丢弃任务（但 HTTP 仍然返回 ok）
                print("[RiskGuard] worker_loop: Enable_RiskGuard=False, skip task.")
                continue

            if not os.path.exists(img_path):
                print("[RiskGuard] file not found:", img_path)
                continue

            ocr_text = ocr_center_text(img_path)
            if not ocr_text:
                print("[RiskGuard] worker_loop: ocr_text empty, skip.")
                continue

            if not has_risk_keyword(ocr_text):
                # 连关键字都没命中，不调大模型，直接跳过
                print("[RiskGuard] worker_loop: no risk keyword in ocr_text, skip.")
                continue

            # ====== 限制大模型调用次数 ======
            if llm_call_count >= LLM_CALL_LIMIT:
                print(
                    f"[RiskGuard] LLM 调用次数已达上限 {LLM_CALL_LIMIT}，"
                    f"跳过本次模型判断：{img_path}"
                )
                continue

            llm_call_count += 1
            print(f"[RiskGuard] 调用第 {llm_call_count} 次大模型进行二次确认...")

            is_risky, llm_comment = call_vision_llm(img_path, ocr_text)
            print(f"[RiskGuard] worker_loop: LLM result is_risky={is_risky}, comment='{llm_comment}'")

            # 如果模型认为没有风险，不做任何处置
            if not is_risky:
                print(
                    f"[RiskGuard] 模型判定为无明显风险，跳过处置。"
                    f" comment={llm_comment} text={ocr_text}"
                )
                continue

            # 模型确认有风险 → 杀进程 + 企微告警
            print(f"[RiskGuard] HIGH RISK: {llm_comment} text={ocr_text}")
            kill_gi_and_btgi()
            send_wecom_alert(ocr_text, llm_comment, img_path)

        except Exception as e:
            print("[RiskGuard] worker error:", e)
        finally:
            task_q.task_done()
            print("[RiskGuard] worker_loop: task_done for", img_path)

# ========== HTTP 接口 ==========
@app.route("/enqueue", methods=["POST"])
def enqueue():
    data = request.get_json(silent=True) or {}
    print("[RiskGuard] /enqueue called, raw data =", data)
    img_path = data.get("path")
    if not img_path:
        print("[RiskGuard] /enqueue: missing 'path' in request.")
        return jsonify({"ok": False, "error": "missing path"}), 400

    # 即使关闭风控，也返回 ok，以免 Producer 报错
    if not ENABLE_RISK_GUARD:
        print("[RiskGuard] /enqueue: Enable_RiskGuard=False, accept but skip.")
        return jsonify({"ok": True, "skipped": True})

    if task_q.full():
        print("[RiskGuard] /enqueue: queue full, size=", task_q.qsize())
        try:
            dropped = task_q.get_nowait()
            task_q.task_done()
            print("[RiskGuard] queue full, drop oldest item:", dropped)
        except queue.Empty:
            print("[RiskGuard] queue full but get_nowait raised Empty")

    task_q.put(img_path)
    print("[RiskGuard] /enqueue: put task, new queue size =", task_q.qsize())
    return jsonify({"ok": True})


@app.route("/health", methods=["GET"])
def health():
    info = {
        "status": "ok",
        "enable_risk_guard": ENABLE_RISK_GUARD,
        "queue_size": task_q.qsize(),
    }
    print("[RiskGuard] /health:", info)
    return jsonify(info)


def main():
    print("[RiskGuard] main() starting worker thread...")
    threading.Thread(target=worker_loop, daemon=True).start()
    print("[RiskGuard] 服务启动于 127.0.0.1:8787/enqueue")
    app.run(host="127.0.0.1", port=8787)


if __name__ == "__main__":
    main()
