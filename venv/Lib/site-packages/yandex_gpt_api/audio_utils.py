#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Утилиты для работы с аудиофайлами в рамках интеграции с Yandex SpeechKit.
"""
import os
import tempfile

# Проверяем наличие pydub для работы с аудио
try:
    from pydub import AudioSegment
    PYDUB_AVAILABLE = True
except ImportError:
    PYDUB_AVAILABLE = False


def convert_to_mono(audio_path):
    """
    Преобразует стерео аудио в моно для корректной работы разметки говорящих.
    
    Args:
        audio_path (str): Путь к аудиофайлу
        
    Returns:
        bytes: Байты моно-аудиофайла в формате MP3
    """
    if not PYDUB_AVAILABLE:
        raise ImportError(
            "Для конвертации аудио в моно требуется библиотека pydub. Установите с помощью: 'uv pip install pydub'"
        )
    
    # Загружаем аудиофайл
    sound = AudioSegment.from_file(audio_path)
    
    # Преобразуем в моно, если это не монофайл
    if sound.channels > 1:
        sound = sound.set_channels(1)
    
    # Сохраняем временный файл в моно
    with tempfile.NamedTemporaryFile(suffix='.mp3', delete=False) as temp:
        temp_path = temp.name
        sound.export(temp_path, format="mp3")
    
    # Читаем байты из временного файла
    with open(temp_path, "rb") as f:
        mono_bytes = f.read()
    
    # Удаляем временный файл
    os.unlink(temp_path)
    
    return mono_bytes


def is_stereo_audio(audio_path):
    """
    Проверяет, является ли аудио стерео (многоканальным).
    
    Args:
        audio_path (str): Путь к аудиофайлу
        
    Returns:
        bool: True, если аудио имеет больше одного канала, иначе False
    """
    if not PYDUB_AVAILABLE:
        raise ImportError(
            "Для проверки аудио требуется библиотека pydub. Установите с помощью: 'uv pip install pydub'"
        )
    
    # Загружаем аудиофайл
    sound = AudioSegment.from_file(audio_path)
    
    # Проверяем количество каналов
    return sound.channels > 1
