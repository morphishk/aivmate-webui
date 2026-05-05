from threading import Thread
import time
import random
from datetime import datetime
import pygame as pg
from live2d import run_live2d
from mmd import run_mmd
from vrm import run_vrm
from web_state import run_state_web
from web_settings import run_settings_web, username, welcome_voice_switch, mate_name
from function import get_lan_url, stop_tts
from tts import play_tts_legacy as play_tts
from llm import chat_preprocess
from archive import _start_archive_timer


import os
ASR_MODE = os.environ.get('ASR_MODE', 'local')

def sense_voice_main():  # 语音交互主线程
    # 浏览器模式下跳过本地麦克风监听，避免无音频设备导致 segfault
    if ASR_MODE == 'browser':
        print("[ASR] 浏览器模式：本地麦克风监听已禁用")
        while True:
            time.sleep(3600)
        return

    from asr import recognize_audio, record_audio, _init_audio_stream, _audio_init_failed
    # 启动时检测一次音频设备，无设备则静默退出，不再轮询
    _init_audio_stream()
    if _audio_init_failed:
        print("[ASR] 未检测到音频输入设备，本地麦克风监听已禁用")
        return

    while True:
        try:
            with open("data/db/current_asr.txt", "r", encoding="utf-8") as f:
                current_asr = f.read()
            if current_asr == "RealTime" or current_asr == "WakeWord":
                say_text = recognize_audio(record_audio())
                if len(say_text) > 1 and current_asr == "RealTime":
                    pg.mixer.init()
                    if pg.mixer.music.get_busy():
                        time.sleep(0.1)
                    else:
                        print(f"{username}：{say_text}")
                        chat_preprocess(say_text)
                elif len(say_text) > 2 and current_asr == "WakeWord" and wake_word in say_text:
                    pg.mixer.init()
                    if pg.mixer.music.get_busy():
                        time.sleep(0.1)
                    else:
                        say_text = say_text.replace(wake_word + "，", "").replace(wake_word, "")
                        print(f"{username}：{say_text}")
                        chat_preprocess(say_text)
            else:
                time.sleep(0.1)
        except Exception:
            time.sleep(0.1)


def text_chat():  # 文本聊天线程
    while True:
        stop_tts()
        msg = ""
        try:
            msg = input(f"{username}：")
        except Exception:
            print("格式错误，请重新输入消息")
            continue
        if msg == "":
            print("请输入内容后再发送")
            continue
        chat_preprocess(msg)


# open_source_project_address:https://github.com/MewCo-AI/ai_virtual_mate_linux
def run_ase():  # 主动感知对话线程
    def ase_chat(msg):
        print(f"{mate_name}主动感知并发起了聊天")
        chat_preprocess(msg)

    def ase_hello():
        current_hour = datetime.now().time().hour
        time_area = {(0, 6): "夜深了睡不着，你来发起聊天话题吧。", (6, 9): "早上好呀，你来发起聊天话题吧。",
                     (9, 11): "上午好呀，你来发起聊天话题吧。", (11, 13): "中午好呀，你来发起聊天话题吧。",
                     (13, 17): "下午好呀，你来发起聊天话题吧。", (17, 19): "傍晚好呀，你来发起聊天话题吧。",
                     (19, 24): "晚上好呀，你来发起聊天话题吧。"}
        for (start, end), hello_msg in time_area.items():
            if start <= current_hour < end:
                ase_chat(hello_msg)
                break

    def ase_news():
        ase_chat("请你完整阅读这些新闻，然后选感兴趣的和我聊聊天，不能选择明星类、负面或令人感到不安的新闻。")

    def ase_weather():
        ase_chat(f"请你结合天气信息，和我发起话题聊聊天，例如提出生活或出行建议")

    def ase_vlm_cam():
        ase_chat("请你读取你看到的摄像头内容，务必根据其中的内容和我聊聊天。")

    def ase_context():
        ase_chat("你是我的有情感的贴心伙伴，请你结合上下文和人设，主动向我发起聊天话题。")

    while True:
        time.sleep(random.randint(180, 600))
        with open("data/db/current_ase.txt", "r", encoding="utf-8") as f:
            current_ase = f.read()
        if current_ase == "on":
            ase_function = random.choice([ase_hello, ase_news, ase_weather, ase_vlm_cam, ase_context])
            print(ase_function)
            ase_function()


def play_welcome():
    try:
        pg.mixer.init()
        pg.mixer.Sound("data/audio/welcome.mp3").play()
        if welcome_voice_switch == "on":
            time.sleep(2)
            play_tts(f"哈喽！{username}，我是{mate_name}，{get_lan_url()}")
    except Exception as e:
        print(f"[Welcome] 音频播放跳过（无音频设备）: {e}")


Thread(target=run_state_web, daemon=True).start()
Thread(target=run_live2d, daemon=True).start()
Thread(target=run_mmd, daemon=True).start()
Thread(target=run_vrm, daemon=True).start()
Thread(target=sense_voice_main, daemon=True).start()
#Thread(target=text_chat, daemon=True).start()
Thread(target=run_ase, daemon=True).start()
Thread(target=run_settings_web, daemon=True).start()
Thread(target=play_welcome, daemon=True).start()
Thread(target=_start_archive_timer, daemon=True).start()
while True:
    time.sleep(1)
