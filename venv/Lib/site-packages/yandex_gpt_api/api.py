#!/usr/bin/env python3
"""
Библиотека для взаимодействия с Yandex GPT API.
Поддерживает синхронный и асинхронный режимы работы, включая потоковую обработку ответов.
Также включает функции для работы с Yandex SpeechKit Speech To Text API v3.
"""
import os
import json
import base64
import requests
import httpx
import asyncio
from typing import AsyncGenerator, List, Dict, Optional, Union, Any
import tempfile

# Импортируем утилиты для работы с аудио
from .audio_utils import convert_to_mono, PYDUB_AVAILABLE, is_stereo_audio

def gpt(auth_headers, messages=None, temperature=0.6, max_tokens=2000):
    """
    Синхронный режим для Yandex GPT.
    
    Args:
        auth_headers: Заголовки аутентификации с API ключом или IAM токеном
        messages: Список сообщений с ключами 'role' и 'text'
        temperature: Контролирует случайность (0.0 до 1.0)
        max_tokens: Максимальное количество токенов для генерации
        
    Returns:
        Строка с ответом от API
    """
    url = 'https://llm.api.cloud.yandex.net/foundationModels/v1/completion'
    
    # Используем предоставленные сообщения или по умолчанию
    if messages is None:
        messages = [
            {
                "role": "system",
                "text": "Вы - полезный ассистент"
            },
            {
                "role": "user",
                "text": "Расскажи короткую историю о роботе"
            }
        ]
    
    # Подготавливаем тело запроса
    request_body = {
        "modelUri": f"gpt://{os.getenv('FOLDER_ID')}/yandexgpt",
        "completionOptions": {
            "stream": False,
            "temperature": temperature,
            "maxTokens": str(max_tokens),
            "reasoningOptions": {
                "mode": "DISABLED"
            }
        },
        "messages": messages
    }
    
    # Выполняем запрос
    response = requests.post(url, headers=auth_headers, json=request_body)
    
    if response.status_code != 200:
        raise RuntimeError(
            f'Invalid response received: code: {response.status_code}, message: {response.text}'
        )
    
    return response.text


async def gpt_async(auth_headers, messages=None, temperature=0.6, max_tokens=2000, timeout=60.0):
    """
    Асинхронная функция для взаимодействия с Yandex GPT API.
    
    Args:
        auth_headers (dict): Заголовки авторизации (IAM-токен или API-ключ)
        messages (list): Список сообщений для обработки
        temperature (float): Температура генерации (от 0 до 1)
        max_tokens (int): Максимальное количество токенов в ответе
        timeout (float): Таймаут запроса в секундах
    
    Returns:
        str: Ответ от API в формате JSON
    """
    if messages is None:
        messages = []
    
    folder_id = os.environ.get('FOLDER_ID')
    if not folder_id:
        return json.dumps({"error": "Не указан FOLDER_ID"})
    
    url = 'https://llm.api.cloud.yandex.net/foundationModels/v1/completion'
    
    request_body = {
        "modelUri": f"gpt://{folder_id}/yandexgpt/latest",
        "completionOptions": {
            "stream": False,
            "temperature": temperature,
            "maxTokens": max_tokens
        },
        "messages": messages
    }
    
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.post(url, headers=auth_headers, json=request_body)
            response.raise_for_status()
            return response.text
    except httpx.ReadTimeout:
        return json.dumps({"error": "Превышено время ожидания ответа от API"})
    except httpx.HTTPStatusError as e:
        return json.dumps({"error": f"Ошибка HTTP: {e.response.status_code}", "details": e.response.text})
    except Exception as e:
        return json.dumps({"error": f"Ошибка при выполнении запроса: {str(e)}"})


def gpt_streaming(auth_headers, messages=None, temperature=0.6, max_tokens=2000, debug=False):
    """
    Синхронная функция для потокового взаимодействия с Yandex GPT API.
    
    Args:
        auth_headers (dict): Заголовки аутентификации
        messages (list, optional): Список сообщений для отправки
        temperature (float, optional): Температура генерации (0.0-1.0)
        max_tokens (int, optional): Максимальное количество токенов в ответе
        debug (bool, optional): Включить отладочный вывод
    
    Yields:
        Текстовые фрагменты по мере их генерации
    """
    url = 'https://llm.api.cloud.yandex.net/foundationModels/v1/completion'
    
    # Используем предоставленные сообщения или по умолчанию
    if messages is None:
        messages = [
            {
                "role": "system",
                "text": "Вы - полезный ассистент"
            },
            {
                "role": "user",
                "text": "Расскажи короткую историю о роботе"
            }
        ]
    
    if debug:
        print(f"URL: {url}")
        print(f"Headers: {auth_headers}")
        print(f"Messages: {messages}")
    
    # Подготавливаем тело запроса с включенным потоковым режимом
    request_body = {
        "modelUri": f"gpt://{os.getenv('FOLDER_ID')}/yandexgpt",
        "completionOptions": {
            "stream": True,
            "temperature": temperature,
            "maxTokens": str(max_tokens)
        },
        "messages": messages
    }
    
    if debug:
        print(f"Request body: {json.dumps(request_body, ensure_ascii=False, indent=2)}")
    
    # Выполняем запрос с потоковым режимом
    response = requests.post(url, headers=auth_headers, json=request_body, stream=True)
    
    if debug:
        print(f"Response status: {response.status_code}")
        print(f"Response headers: {response.headers}")
    
    if response.status_code != 200:
        error_message = f'Invalid response received: code: {response.status_code}, message: {response.text}'
        if debug:
            print(f"Error: {error_message}")
        raise RuntimeError(error_message)
    
    # Обрабатываем потоковый ответ
    last_text = ""
    buffer = b""
    
    # Итерируемся по чанкам ответа
    for chunk in response.iter_content(chunk_size=1024):
        if not chunk:
            continue
            
        if debug:
            print(f"Received chunk of size: {len(chunk)} bytes")
        
        # Добавляем чанк в буфер
        buffer += chunk
        
        try:
            # Пытаемся декодировать буфер
            text = buffer.decode('utf-8')
            
            # Проверяем, есть ли в буфере полные JSON-объекты
            try:
                # Пытаемся найти полные JSON-объекты в буфере
                data = json.loads(text)
                
                if debug:
                    print(f"Parsed JSON: {json.dumps(data, ensure_ascii=False)[:200]}...")
                
                # Извлекаем текст из структуры ответа
                if 'result' in data and 'alternatives' in data['result']:
                    for alt in data['result']['alternatives']:
                        if 'message' in alt and 'text' in alt['message']:
                            current_text = alt['message']['text']
                            
                            if debug:
                                print(f"Current text: {current_text}")
                            
                            # Если это первый фрагмент или полностью новый текст
                            if not last_text:
                                if debug:
                                    print(f"First fragment: {current_text}")
                                yield current_text
                                last_text = current_text
                            # Если текст изменился, выдаем только новую часть
                            elif current_text != last_text:
                                if current_text.startswith(last_text):
                                    new_part = current_text[len(last_text):]
                                    if new_part:
                                        if debug:
                                            print(f"New part: {new_part}")
                                        yield new_part
                                else:
                                    if debug:
                                        print(f"Completely new text: {current_text}")
                                    yield current_text
                                last_text = current_text
                
                # Очищаем буфер после успешной обработки
                buffer = b""
            except json.JSONDecodeError:
                # Если не удалось разобрать JSON, возможно, это неполный чанк
                if debug:
                    print("Incomplete JSON, waiting for more data")
                # Оставляем данные в буфере для следующей итерации
        except UnicodeDecodeError:
            # Если не удалось декодировать, продолжаем накапливать байты
            if debug:
                print("Unicode decode error, waiting for more data")


async def gpt_streaming_httpx(auth_headers, messages=None, temperature=0.6, max_tokens=2000, timeout=60.0):
    """
    Асинхронная функция для потокового взаимодействия с Yandex GPT API с использованием httpx.
    
    Args:
        auth_headers (dict): Заголовки авторизации (IAM-токен или API-ключ)
        messages (list): Список сообщений для обработки
        temperature (float): Температура генерации (от 0 до 1)
        max_tokens (int): Максимальное количество токенов в ответе
        timeout (float): Таймаут запроса в секундах
    
    Yields:
        str: Фрагменты ответа от API
    """
    if messages is None:
        messages = []
    
    folder_id = os.environ.get('FOLDER_ID')
    if not folder_id:
        yield "Ошибка: Не указан FOLDER_ID"
        return
    
    url = 'https://llm.api.cloud.yandex.net/foundationModels/v1/completion'
    
    request_body = {
        "modelUri": f"gpt://{folder_id}/yandexgpt/latest",
        "completionOptions": {
            "stream": True,
            "temperature": temperature,
            "maxTokens": max_tokens
        },
        "messages": messages
    }
    
    try:
        # Для отслеживания уже полученного текста
        full_text = ""
        
        async with httpx.AsyncClient(timeout=timeout) as client:
            async with client.stream('POST', url, headers=auth_headers, json=request_body) as response:
                response.raise_for_status()
                async for chunk in response.aiter_lines():
                    if chunk.strip():
                        # Пропускаем пустые строки
                        if not chunk or chunk == 'data: [DONE]':
                            continue
                            
                        try:
                            # Обрабатываем строку JSON
                            if chunk.startswith('data: '):
                                json_str = chunk[6:]  # Убираем префикс 'data: '
                                data = json.loads(json_str)
                                
                                if 'result' in data and 'alternatives' in data['result']:
                                    for alt in data['result']['alternatives']:
                                        if 'message' in alt and 'text' in alt['message']:
                                            current_text = alt['message']['text']
                                            
                                            # Выдаем только новую часть текста
                                            if len(current_text) > len(full_text):
                                                new_text = current_text[len(full_text):]
                                                if new_text:  # Проверяем, что есть новый текст
                                                    full_text = current_text
                                                    yield new_text
                            else:
                                # Если это не JSON с префиксом 'data: ', просто выдаем как есть
                                yield chunk
                        except json.JSONDecodeError:
                            # Если не удалось разобрать JSON, выдаем как есть
                            if chunk.startswith('data: '):
                                yield chunk[6:]
                            else:
                                yield chunk
    except httpx.ReadTimeout:
        yield "\nОшибка: Превышено время ожидания ответа от API"
    except httpx.HTTPStatusError as e:
        yield f"\nОшибка HTTP: {e.response.status_code}"
    except Exception as e:
        yield f"\nОшибка при выполнении запроса: {str(e)}"


def stt_recognize_file(auth_headers, content=None, uri=None, model=None, audio_format=None, 
                      text_normalization=None, language_restriction=None, audio_processing_type=None,
                      recognition_classifier=None, speech_analysis=None, speaker_labeling=None):
    """
    Синхронная функция для отправки файла на распознавание через Yandex SpeechKit STT v3 API.
    
    Args:
        auth_headers (dict): Заголовки аутентификации с API ключом или IAM токеном
        content (bytes, optional): Байты с аудиоданными
        uri (str, optional): S3 URL к аудиоданным
        model (str, optional): Название модели распознавания
        audio_format (dict, optional): Параметры аудиоформата
        text_normalization (dict, optional): Параметры нормализации текста
        language_restriction (dict, optional): Параметры ограничения языка
        audio_processing_type (str, optional): Тип обработки аудио
        recognition_classifier (dict, optional): Параметры классификатора распознавания
        speech_analysis (dict, optional): Параметры анализа речи
        speaker_labeling (dict, optional): Параметры определения спикеров
        
    Returns:
        dict: Словарь с operationId для дальнейшего получения результата
    """
    if content is None and uri is None:
        raise ValueError("Необходимо указать либо content, либо uri")
        
    url = 'https://stt.api.cloud.yandex.net/stt/v3/recognizeFileAsync'
    
    # Подготавливаем тело запроса
    request_body = {}
    
    if content is not None:
        if isinstance(content, str):
            with open(content, 'rb') as f:
                content = f.read()
        # Кодируем байты в base64 для отправки через JSON
        request_body["content"] = base64.b64encode(content).decode('utf-8')
    else:
        request_body["uri"] = uri
    
    # Настройки модели распознавания
    recognition_model = {}
    
    if model:
        recognition_model["model"] = model
    
    if audio_format:
        recognition_model["audioFormat"] = audio_format
    
    if text_normalization:
        recognition_model["textNormalization"] = text_normalization
    
    if language_restriction:
        recognition_model["languageRestriction"] = language_restriction
    
    if audio_processing_type:
        recognition_model["audioProcessingType"] = audio_processing_type
    
    if recognition_model:
        request_body["recognitionModel"] = recognition_model
    
    if recognition_classifier:
        request_body["recognitionClassifier"] = recognition_classifier
    
    if speech_analysis:
        request_body["speechAnalysis"] = speech_analysis
    
    if speaker_labeling:
        request_body["speakerLabeling"] = speaker_labeling
    
    # Выполняем запрос
    response = requests.post(url, headers=auth_headers, json=request_body)
    
    if response.status_code != 200:
        raise RuntimeError(
            f'Invalid response received: code: {response.status_code}, message: {response.text}'
        )
    
    return response.json()


async def stt_recognize_file_async(auth_headers, content=None, uri=None, model=None, audio_format=None, 
                                  text_normalization=None, language_restriction=None, audio_processing_type=None,
                                  recognition_classifier=None, speech_analysis=None, speaker_labeling=None,
                                  timeout=60.0):
    """
    Асинхронная функция для отправки файла на распознавание через Yandex SpeechKit STT v3 API.
    
    Args:
        auth_headers (dict): Заголовки аутентификации с API ключом или IAM токеном
        content (bytes или str, optional): Байты с аудиоданными или путь к файлу
        uri (str, optional): S3 URL к аудиоданным
        model (str, optional): Название модели распознавания
        audio_format (dict, optional): Параметры аудиоформата
        text_normalization (dict, optional): Параметры нормализации текста
        language_restriction (dict, optional): Параметры ограничения языка
        audio_processing_type (str, optional): Тип обработки аудио
        recognition_classifier (dict, optional): Параметры классификатора распознавания
        speech_analysis (dict, optional): Параметры анализа речи
        speaker_labeling (dict, optional): Параметры определения спикеров
        timeout (float, optional): Таймаут запроса в секундах
        
    Returns:
        dict: Словарь с operationId для дальнейшего получения результата
    """
    if content is None and uri is None:
        raise ValueError("Необходимо указать либо content, либо uri")
        
    url = 'https://stt.api.cloud.yandex.net/stt/v3/recognizeFileAsync'
    
    # Подготавливаем тело запроса
    request_body = {}
    
    if content is not None:
        if isinstance(content, str):
            # Если content - путь к файлу, читаем его содержимое
            with open(content, 'rb') as f:
                content = f.read()
        # Кодируем байты в base64 для отправки через JSON
        request_body["content"] = base64.b64encode(content).decode('utf-8')
    else:
        request_body["uri"] = uri
    
    # Настройки модели распознавания
    recognition_model = {}
    
    if model:
        recognition_model["model"] = model
    
    if audio_format:
        recognition_model["audioFormat"] = audio_format
    
    if text_normalization:
        recognition_model["textNormalization"] = text_normalization
    
    if language_restriction:
        recognition_model["languageRestriction"] = language_restriction
    
    if audio_processing_type:
        recognition_model["audioProcessingType"] = audio_processing_type
    
    if recognition_model:
        request_body["recognitionModel"] = recognition_model
    
    if recognition_classifier:
        request_body["recognitionClassifier"] = recognition_classifier
    
    if speech_analysis:
        request_body["speechAnalysis"] = speech_analysis
    
    if speaker_labeling:
        request_body["speakerLabeling"] = speaker_labeling
    
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.post(url, headers=auth_headers, json=request_body)
            response.raise_for_status()
            return response.json()
    except httpx.ReadTimeout:
        return {"error": "Превышено время ожидания ответа от API"}
    except httpx.HTTPStatusError as e:
        return {"error": f"Ошибка HTTP: {e.response.status_code}", "details": e.response.text}
    except Exception as e:
        return {"error": f"Ошибка при выполнении запроса: {str(e)}"}


def stt_get_recognition(auth_headers, operation_id):
    """
    Синхронная функция для получения результатов распознавания по operationId через Yandex SpeechKit STT v3 API.
    
    Args:
        auth_headers (dict): Заголовки аутентификации с API ключом или IAM токеном
        operation_id (str): Идентификатор операции распознавания
        
    Returns:
        dict: Словарь с результатами распознавания
    """
    url = f'https://stt.api.cloud.yandex.net/stt/v3/getRecognition?operationId={operation_id}'
    
    try:
        # Выполняем запрос
        response = requests.get(url, headers=auth_headers)
        
        if response.status_code != 200:
            return {
                'error': f'Invalid response received: code: {response.status_code}',
                'details': response.text
            }
        
        # Аккуратно парсим JSON, обрабатывая возможные ошибки
        try:
            return response.json()
        except json.JSONDecodeError as e:
            # Если получили ошибку при парсинге JSON, возможно, нужно очистить от лишних данных
            text = response.text
            # Попытка найти первую валидную JSON-строку
            try:
                first_json = text.strip().split('\n')[0]
                return json.loads(first_json)
            except (json.JSONDecodeError, IndexError):
                return {
                    'error': f'Не удалось распарсить ответ: {str(e)}',
                    'raw_response': text[:1000]  # Возвращаем первую часть ответа для диагностики
                }
    except Exception as e:
        return {'error': f'Ошибка при выполнении запроса: {str(e)}'}


async def stt_get_recognition_async(auth_headers, operation_id, timeout=60.0):
    """
    Асинхронная функция для получения результатов распознавания по operationId через Yandex SpeechKit STT v3 API.
    
    Args:
        auth_headers (dict): Заголовки аутентификации с API ключом или IAM токеном
        operation_id (str): Идентификатор операции распознавания
        timeout (float, optional): Таймаут запроса в секундах
        
    Returns:
        dict: Словарь с результатами распознавания
    """
    url = f'https://stt.api.cloud.yandex.net/stt/v3/getRecognition?operationId={operation_id}'
    
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.get(url, headers=auth_headers)
            
            if response.status_code != 200:
                return {
                    'error': f'Invalid response received: code: {response.status_code}',
                    'details': response.text
                }
            
            # Аккуратно парсим JSON, обрабатывая возможные ошибки
            try:
                return response.json()
            except json.JSONDecodeError as e:
                # Если получили ошибку при парсинге JSON, возможно, нужно очистить от лишних данных
                text = response.text
                # Попытка найти первую валидную JSON-строку
                try:
                    first_json = text.strip().split('\n')[0]
                    return json.loads(first_json)
                except (json.JSONDecodeError, IndexError):
                    return {
                        'error': f'Не удалось распарсить ответ: {str(e)}',
                        'raw_response': text[:1000]  # Возвращаем первую часть ответа для диагностики
                    }
    except httpx.ReadTimeout:
        return {"error": "Превышено время ожидания ответа от API"}
    except httpx.HTTPStatusError as e:
        return {"error": f"Ошибка HTTP: {e.response.status_code}", "details": e.response.text}
    except Exception as e:
        return {"error": f"Ошибка при выполнении запроса: {str(e)}"}


# Функция convert_to_mono перенесена в модуль audio_utils


def stt_recognize_with_speaker_labeling(auth_headers, content=None, uri=None, model="general:rc", channel_tag=None, 
                             audio_format=None, convert_stereo_to_mono=True):
    """
    Удобная функция для распознавания речи с разметкой говорящих (speaker labeling).
    
    Args:
        auth_headers (dict): Заголовки аутентификации с API ключом или IAM токеном
        content (bytes или str, optional): Байты с аудиоданными или путь к файлу
        uri (str, optional): S3 URL к аудиоданным
        model (str, optional): Название модели распознавания, по умолчанию "general:rc"
        channel_tag (str, optional): Метка канала для разделения дикторов (0 или 1)
        audio_format (dict, optional): Параметры аудиоформата. По умолчанию MP3.
        convert_stereo_to_mono (bool, optional): Автоматически конвертировать стерео в моно, если путь к файлу.
        
    Returns:
        dict: Словарь с operationId для дальнейшего получения результата
    """
    # Настройка параметров для разметки говорящих
    speaker_labeling = {
        "speakerLabeling": "SPEAKER_LABELING_ENABLED"  # Включаем разметку говорящих
    }
    
    # Настраиваем модель распознавания с полным режимом данных (FULL_DATA)
    audio_processing_type = "FULL_DATA"  # Необходимо для разметки говорящих
    
    # Если указан channel_tag, добавляем его в запрос
    if channel_tag is not None:
        speaker_labeling["channelTag"] = channel_tag
    
    # Проверяем и конвертируем аудио, если это стерео файл
    if convert_stereo_to_mono and isinstance(content, str) and PYDUB_AVAILABLE:
        try:
            # Проверяем является ли файл стерео
            if is_stereo_audio(content):
                print(f"Обнаружен стерео аудиофайл, конвертирую в моно: {content}")
                content = convert_to_mono(content)
                uri = None  # Если у нас был URI, теперь мы используем байты
        except Exception as e:
            print(f"Ошибка при конвертации стерео в моно: {e}")
    
    # Если формат не указан, используем MP3 по умолчанию и указываем монозвучание
    if audio_format is None:
        audio_format = {
            "containerAudio": {
                "containerAudioType": "MP3"
            },
            "audioChannelCount": 1  # Явно указываем обработку как моно для разметки говорящих
        }
    elif "audioChannelCount" not in audio_format:
        audio_format["audioChannelCount"] = 1  # Добавляем моноформат, если не указан
    
    # Вызываем основную функцию с настройками для разметки говорящих
    return stt_recognize_file(
        auth_headers=auth_headers,
        content=content,
        uri=uri,
        model=model,
        audio_format=audio_format,
        audio_processing_type=audio_processing_type,
        speaker_labeling=speaker_labeling
    )


async def stt_recognize_with_speaker_labeling_async(auth_headers, content=None, uri=None, model="general:rc", 
                                                 channel_tag=None, audio_format=None, convert_stereo_to_mono=True, timeout=60.0):
    """
    Асинхронная удобная функция для распознавания речи с разметкой говорящих (speaker labeling).
    
    Args:
        auth_headers (dict): Заголовки аутентификации с API ключом или IAM токеном
        content (bytes или str, optional): Байты с аудиоданными или путь к файлу
        uri (str, optional): S3 URL к аудиоданным
        model (str, optional): Название модели распознавания, по умолчанию "general:rc"
        channel_tag (str, optional): Метка канала для разделения дикторов (0 или 1)
        audio_format (dict, optional): Параметры аудиоформата. По умолчанию MP3.
        convert_stereo_to_mono (bool, optional): Автоматически конвертировать стерео в моно, если путь к файлу.
        timeout (float, optional): Таймаут запроса в секундах
        
    Returns:
        dict: Словарь с operationId для дальнейшего получения результата
    """
    # Настройка параметров для разметки говорящих
    speaker_labeling = {
        "speakerLabeling": "SPEAKER_LABELING_ENABLED"  # Включаем разметку говорящих
    }
    
    # Настраиваем модель распознавания с полным режимом данных (FULL_DATA)
    audio_processing_type = "FULL_DATA"  # Необходимо для разметки говорящих
    
    # Если указан channel_tag, добавляем его в запрос
    if channel_tag is not None:
        speaker_labeling["channelTag"] = channel_tag
    
    # Проверяем и конвертируем аудио, если это стерео файл
    if convert_stereo_to_mono and isinstance(content, str) and PYDUB_AVAILABLE:
        try:
            # Проверяем является ли файл стерео
            if is_stereo_audio(content):
                print(f"Обнаружен стерео аудиофайл, конвертирую в моно: {content}")
                content = convert_to_mono(content)
                uri = None  # Если у нас был URI, теперь мы используем байты
        except Exception as e:
            print(f"Ошибка при конвертации стерео в моно: {e}")
    
    # Если формат не указан, используем MP3 по умолчанию и указываем монозвучание
    if audio_format is None:
        audio_format = {
            "containerAudio": {
                "containerAudioType": "MP3"
            },
            "audioChannelCount": 1  # Явно указываем обработку как моно для разметки говорящих
        }
    elif "audioChannelCount" not in audio_format:
        audio_format["audioChannelCount"] = 1  # Добавляем моноформат, если не указан
    
    # Вызываем асинхронную функцию с настройками для разметки говорящих
    return await stt_recognize_file_async(
        auth_headers=auth_headers,
        content=content,
        uri=uri,
        model=model,
        audio_format=audio_format,
        audio_processing_type=audio_processing_type,
        speaker_labeling=speaker_labeling,
        timeout=timeout
    )
