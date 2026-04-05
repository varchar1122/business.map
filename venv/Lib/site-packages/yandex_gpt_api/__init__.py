"""
Библиотека для работы с Yandex GPT API и SpeechKit STT API.

Предоставляет функции для синхронного и асинхронного взаимодействия с API,
включая потоковый режим для получения ответов от GPT по мере их генерации
и функции для распознавания речи через SpeechKit STT v3.
"""

from .api import (
    gpt, gpt_streaming, gpt_async, gpt_streaming_httpx,
    stt_recognize_file, stt_recognize_file_async,
    stt_get_recognition, stt_get_recognition_async,
    stt_recognize_with_speaker_labeling, stt_recognize_with_speaker_labeling_async
)

__all__ = [
    'gpt', 'gpt_streaming', 'gpt_async', 'gpt_streaming_httpx',
    'stt_recognize_file', 'stt_recognize_file_async',
    'stt_get_recognition', 'stt_get_recognition_async',
    'stt_recognize_with_speaker_labeling', 'stt_recognize_with_speaker_labeling_async'
]
