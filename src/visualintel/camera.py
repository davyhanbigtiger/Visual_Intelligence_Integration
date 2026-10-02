"""Local camera demo: live preview and one outstanding inference at a time."""
import base64
import json
import queue
import threading
import time
import tkinter as tk
from tkinter import ttk

import cv2

from visualintel.engine import SCENE_PROMPT, call_model, check_ollama_ready, resize_encoded_image
from visualintel.structured import FACTUAL_SCHEMA


def analyze_frame(frame, model="minicpm-v4.6", max_side=640):
    ok, encoded = cv2.imencode(".jpg", frame)
    if not ok:
        raise ValueError("Cannot encode camera frame")
    image = resize_encoded_image(encoded.tobytes(), max_side)
    raw = call_model([base64.b64encode(image).decode("ascii")], SCENE_PROMPT,
                     model=model, timeout=60, response_schema=FACTUAL_SCHEMA,
                     generation_options={"temperature": 0, "seed": 42, "num_predict": 96})
    return json.loads(raw)["answer"]


def run_camera(index=0, model="minicpm-v4.6", max_side=640, backend="dshow"):
    check_ollama_ready(model=model)
    api = {"dshow": cv2.CAP_DSHOW, "msmf": cv2.CAP_MSMF, "auto": cv2.CAP_ANY}[backend]
    cap = cv2.VideoCapture(index, api)
    if not cap.isOpened():
        cap.release()
        raise ValueError("Cannot open camera. Check Windows camera permissions, camera index, "
                         "other camera apps, or try --backend msmf.")
    root = None
    try:
        root = tk.Tk()
        root.title("VisualIntelligence — 摄像头测试")
        preview = ttk.Label(root)
        preview.pack(padx=12, pady=8)
        snapshot = ttk.Label(root, text="待分析帧")
        snapshot.pack()
        status = tk.StringVar(value=f"{model} | 点击分析；不保存图片或视频")
        ttk.Label(root, textvariable=status, wraplength=760).pack(padx=12, pady=8)
        answer = tk.Text(root, height=5, width=90, wrap="word")
        answer.pack(padx=12, pady=8)
        controls = ttk.Frame(root)
        controls.pack(pady=8)
        auto = tk.BooleanVar(value=False)
        ttk.Checkbutton(controls, text="连续分析（完成后等待 2 秒再取最新帧）", variable=auto).pack(side="left")
        events = queue.Queue()
        state = {"frame": None, "busy": False, "closed": False, "next": 0.0,
                 "captured": 0.0, "last_capture": None}

        def photo(frame, side):
            height, width = frame.shape[:2]
            scale = min(1, side / max(height, width))
            rgb = cv2.cvtColor(cv2.resize(frame, (max(1, round(width * scale)),
                                                  max(1, round(height * scale)))), cv2.COLOR_BGR2RGB)
            h, w = rgb.shape[:2]
            return tk.PhotoImage(data=f"P6\n{w} {h}\n255\n".encode() + rgb.tobytes(), format="PPM")

        def submit():
            if state["busy"] or state["frame"] is None:
                return
            frame = state["frame"].copy()
            state["busy"] = True
            state["captured"] = time.monotonic()
            state["last_capture"] = state["captured"]
            snapshot.image = photo(frame, 240)
            snapshot.configure(image=snapshot.image)
            button.configure(state="disabled")
            answer.delete("1.0", "end")

            def worker():
                started = time.monotonic()
                try:
                    result = analyze_frame(frame, model, max_side)
                    events.put((True, result, time.monotonic() - started))
                except Exception as exc:
                    events.put((False, str(exc), time.monotonic() - started))
            threading.Thread(target=worker, daemon=True).start()

        button = ttk.Button(controls, text="分析当前画面", command=submit)
        button.pack(side="left", padx=12)

        def close():
            state["closed"] = True
            cap.release()
            root.destroy()

        root.protocol("WM_DELETE_WINDOW", close)
        root.bind("<Escape>", lambda event: close())

        def tick():
            if state["closed"]:
                return
            ok, frame = cap.read()
            if not ok:
                state["frame"] = None
                auto.set(False)
                button.configure(state="disabled")
                status.set("摄像头读取失败；请关闭窗口并检查摄像头连接。")
                root.after(500, tick)
                return
            state["frame"] = frame
            preview.image = photo(frame, 640)
            preview.configure(image=preview.image)
            if not state["busy"]:
                button.configure(state="normal")
            try:
                success, result, elapsed = events.get_nowait()
                state["busy"] = False
                state["next"] = time.monotonic() + 2
                button.configure(state="normal")
                answer.insert("end", result if success else f"分析失败：{result}")
                state["result_label"] = f"{'完成' if success else '失败'}，耗时 {elapsed:.2f} 秒"
                if not success:
                    auto.set(False)
            except queue.Empty:
                pass
            now = time.monotonic()
            if state["busy"]:
                status.set(f"分析中 {now - state['captured']:.1f} 秒；下方小图是提交帧，预览继续更新")
            elif state["last_capture"] is not None:
                status.set(f"{state.get('result_label', '')}；结果对应 {now - state['last_capture']:.1f} 秒前的帧")
            if auto.get() and not state["busy"] and now >= state["next"]:
                submit()
            root.after(50, tick)

        tick()
        root.mainloop()
    finally:
        cap.release()
        if root is not None:
            try:
                root.destroy()
            except tk.TclError:
                pass
    return 0
