# -*- coding: utf-8 -*-
import json
import os
import re

import requests
from ddgs import DDGS
from dotenv import load_dotenv
from yandex_gpt_api import gpt

load_dotenv()

# Правила для всех ответов пользователю и промежуточных шагов (только факты из источников)
_GROUNDING_CORE = (
    "КРИТИЧЕСКОЕ ПРАВИЛО: не используй внешние знания, догадки и типовые отраслевые шаблоны. "
    "Любой факт, название, цифра, утверждение о компании или рынке должны прямо следовать из переданного "
    "текста (анкета пользователя и/или фрагменты страниц из интернета). Если чего-то нет в источниках — "
    "пиши явно: «в переданных данных об этом нет» и не заполняй пробел вымыслом. "
    "Не придумывай отзывы, рейтинги, выручку, долю рынка, новости и юридические детали."
)

# Лимит UTF-8 байт на запрос к Yandex (в документации до 500000)
_MAX_PAYLOAD_UTF8 = 400_000
_MAX_SYSTEM_UTF8 = 20_000
_MAX_PAGE_EXCERPT_UTF8 = 22_000
_MAX_COMPETITOR_JSON_UTF8 = 320_000
_MAX_SURVEY_JSON_UTF8 = 48_000
_MAX_COMPETITOR_ANALYSIS_UTF8 = 80_000


def _normalize_survey_dict(query_data):
    """Единая схема анкеты для промптов (в т.ч. необязательное поле additionalInfo)."""
    if not isinstance(query_data, dict):
        query_data = {}
    return {
        "region": str(query_data.get("region") or "").strip(),
        "companyName": str(query_data.get("companyName") or "").strip(),
        "businessType": str(query_data.get("businessType") or "").strip(),
        "website": str(query_data.get("website") or "").strip(),
        "additionalInfo": str(query_data.get("additionalInfo") or "").strip(),
    }


def _utf8_len(s):
    return len(str(s).encode("utf-8"))


def truncate_utf8(text, max_bytes):
    if text is None:
        return ""
    s = str(text)
    if _utf8_len(s) <= max_bytes:
        return s
    suffix = "\n\n...[обрезано]"
    budget = max(0, max_bytes - _utf8_len(suffix))
    lo, hi = 0, len(s)
    while lo < hi:
        mid = (lo + hi + 1) // 2
        if _utf8_len(s[:mid]) <= budget:
            lo = mid
        else:
            hi = mid - 1
    return s[:lo] + suffix


def html_to_plain_text(html, max_scan_chars=1_500_000):
    s = str(html)[:max_scan_chars]
    s = re.sub(r"<script[\s\S]*?</script>", " ", s, flags=re.I)
    s = re.sub(r"<style[\s\S]*?</style>", " ", s, flags=re.I)
    s = re.sub(r"<[^>]+>", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def clamp_messages(messages, max_total_utf8=_MAX_PAYLOAD_UTF8):
    """Один system + один user; суммарный размер текста в байтах UTF-8 ограничен."""
    systems = [m for m in messages if m.get("role") == "system"]
    users = [m for m in messages if m.get("role") != "system"]
    out = []
    used = 0
    for m in systems:
        t = truncate_utf8(m.get("text", ""), min(_MAX_SYSTEM_UTF8, max_total_utf8 - used))
        out.append({"role": "system", "text": t})
        used += _utf8_len(t)
    combined = "\n\n".join(str(m.get("text", "") or "") for m in users) if users else ""
    combined = truncate_utf8(combined, max(4000, max_total_utf8 - used))
    out.append({"role": "user", "text": combined})
    return out


def safe_gpt(headers, messages, **kwargs):
    return gpt(headers, clamp_messages(messages), **kwargs)


def parse_gpt_response_text(response_text):
    if response_text is None:
        return ""
    if isinstance(response_text, dict):
        data = response_text
    else:
        s = str(response_text).strip()
        if not s:
            return ""
        try:
            data = json.loads(s)
        except json.JSONDecodeError:
            return s
    try:
        return data["result"]["alternatives"][0]["message"]["text"].strip()
    except (KeyError, IndexError, TypeError):
        return str(response_text).strip()


def _fetch_competitor_pages(urls, max_pages=8):
    pages = []
    for url in urls[:max_pages]:
        if not url or "http" not in url:
            continue
        try:
            r = requests.get(
                url,
                timeout=18,
                headers={"User-Agent": "Mozilla/5.0 (compatible; BusinessMapBot/1.0)"},
            )
            plain = html_to_plain_text(r.text)
            excerpt = truncate_utf8(plain, _MAX_PAGE_EXCERPT_UTF8)
        except requests.RequestException:
            excerpt = ""
        pages.append({"url": url, "excerpt": excerpt})
    return pages


def get_links(response_text):
    search_query = parse_gpt_response_text(response_text)
    if not search_query:
        raise ValueError("Пустой поисковый запрос: не удалось извлечь текст из ответа модели")

    with DDGS() as ddgs:
        results = list(ddgs.text(search_query, max_results=10))

    urls = []
    for i in results:
        href = i.get("href") or ""
        if "http" in href:
            urls.append(href)

    pages = _fetch_competitor_pages(urls)
    return ai_answer(pages)


def ai_answer(pages):
    """Анализ фрагментов страниц конкурентов (опрос пользователя здесь не передаётся)."""
    api_key = os.getenv("API_KEY")
    answer = None

    headers = {
        "Authorization": f"Api-Key {api_key}",
        "Content-Type": "application/json",
    }

    payload = json.dumps(pages, ensure_ascii=False)
    payload = truncate_utf8(payload, _MAX_COMPETITOR_JSON_UTF8)

    messages = [
        {
            "role": "system",
            "text": (
                "Ты аналитик. Тебе дают только JSON: объекты {'url', 'excerpt'} — ссылка и фрагмент текста, "
                "загруженный из интернета. " + _GROUNDING_CORE + " "
                "Если excerpt пустой — не описывай содержание сайта; напиши, что фрагмент не получен. "
                "Формулировки вроде «вероятно», «обычно в отрасли» без цитаты из excerpt запрещены."
            ),
        },
        {
            "role": "user",
            "text": (
                "Данные только из выдачи поиска и загруженных страниц:\n"
                f"{payload}\n\n"
                "Сделай (только по excerpt; пустой excerpt = нет данных по сайту):\n"
                "1) Что можно сказать о каждом URL строго по его excerpt (без догадок).\n"
                "2) Общее/отличия — только если это видно из текстов excerpt; иначе укажи, что сравнить нельзя.\n"
                "3) Список всех переданных URL в конце отдельным блоком."
            ),
        },
    ]

    response_text = safe_gpt(headers, messages, temperature=0.2, max_tokens=2000)

    try:
        response_json = json.loads(response_text)
        if "result" in response_json and "alternatives" in response_json["result"]:
            for alt in response_json["result"]["alternatives"]:
                if "message" in alt and "text" in alt["message"]:
                    answer = alt["message"]["text"]
                    break
    except json.JSONDecodeError:
        answer = response_text

    return answer


def get_query(query_data):
    """
    Пайплайн: опрос → поисковый запрос (LLM) → поиск сайтов → загрузка страниц → анализ конкурентов (LLM)
    → итоговый отчёт для пользователя (LLM): конкуренты, плюсы/минусы его бизнеса, советы.
    """
    api_key = os.getenv("API_KEY")
    headers = {
        "Authorization": f"Api-Key {api_key}",
        "Content-Type": "application/json",
    }

    survey = _normalize_survey_dict(query_data)
    survey_for_prompt = truncate_utf8(
        json.dumps(survey, ensure_ascii=False),
        _MAX_SURVEY_JSON_UTF8,
    )

    messages_search = [
        {
            "role": "system",
            "text": (
                "Ты составляешь поисковый запрос для поисковой системы. Анкета в JSON с полями: "
                "region, companyName, businessType, website, additionalInfo (последние два могут быть пустыми). "
                "Разрешены только слова и формулировки из этих полей: регион/сфера/сайт/свободный текст в additionalInfo. "
                + _GROUNDING_CORE
                + " Не добавляй термины и локации, которых нет в JSON."
            ),
        },
        {
            "role": "user",
            "text": (
                f"Анкета (единственный источник смысла запроса), JSON:\n{survey_for_prompt}\n\n"
                "Выведи одну строку — поисковый запрос на русском: ключевые слова для поиска похожих компаний/услуг.\n"
                "- Поле additionalInfo — дополнительные сведения в словах пользователя: при непустом значении включи в запрос "
                "только ключевые слова из этого текста, без искажений и без новых фактов.\n"
                "- Не включай юридическое название из companyName.\n"
                "Без слов «сайт», «страница», без пояснений."
            ),
        },
    ]

    response_text = safe_gpt(headers, messages_search, temperature=0.2, max_tokens=400)
    competitor_analysis = get_links(response_text)

    analysis_for_final = truncate_utf8(
        competitor_analysis or "",
        _MAX_COMPETITOR_ANALYSIS_UTF8,
    )

    messages_final = [
        {
            "role": "system",
            "text": (
                "Ты готовишь отчёт для владельца бизнеса. Разрешены ровно два типа источников: "
                "(1) JSON-анкета: region, companyName, businessType, website и при наличии additionalInfo — "
                "дополнительный текст, который пользователь указал сам; это его формулировки, не независимая проверка рынка; "
                "(2) блок про конкурентов — только из загруженных из интернета фрагментов страниц (сайты целиком ты не видел). "
                + _GROUNDING_CORE
                + " Плюсы, минусы и советы допустимы только как прямые логические следствия из этих двух источников; "
                "если связь неочевидна — не включай пункт, укажи «недостаточно данных в источниках». "
                "Советы формулируй как «рассмотрите X», если X явно следует из фрагментов конкурентов или из явного сравнения анкеты с источником 2; "
                "не добавляй общие рекомендации «как обычно делают в бизнесе» без привязки к тексту."
            ),
        },
        {
            "role": "user",
            "text": (
                f"### Источник 1 — анкета пользователя (JSON)\n{survey_for_prompt}\n\n"
                f"### Источник 2 — сводка по конкурентам (только из интернет-фрагментов)\n{analysis_for_final}\n\n"
                "Составь отчёт. Не добавляй факты вне двух источников выше.\n\n"
                "## Кратко о бизнесе пользователя (из полей анкеты; если заполнено additionalInfo — отрази смысл как "
                "собственные пометки пользователя, без домыслов сверх текста)\n"
                "## Что сказано о конкурентах (только из источника 2; если там пусто — так и напиши)\n"
                "## Плюсы позиции пользователя (только если выводимы из анкеты и/или явного сравнения с источником 2)\n"
                "## Минусы и риски (только если выводимы из тех же данных; иначе раздел: недостаточно данных)\n"
                "## 3–5 шагов по улучшению (каждый шаг должен опираться на формулировки из источника 2 или на явное "
                "противопоставление анкеты и источника 2; иначе не включай пункт)\n"
                "## URL конкурентов из источника 2 (скопируй список, если он там есть)\n"
            ),
        },
    ]

    response_text = safe_gpt(headers, messages_final, temperature=0.25, max_tokens=3500)
    body = parse_gpt_response_text(response_text)
    notice = (
        "Источники отчёта: ваши ответы в анкете (включая при необходимости поле «дополнительная информация») и фрагменты "
        "текста со страниц сайтов, найденных в интернете по поисковому запросу. Сведения не подтягиваются из других баз "
        "и не дополняются домыслами; при неполных данных в отчёте будут пропуски.\n\n"
    )
    return notice + (body or "")


if __name__ == "__main__":
    demo = get_query(
        {
            "region": "Москва",
            "companyName": "ООО Тест",
            "businessType": "IT-аутсорсинг",
            "website": "",
            "additionalInfo": "Фокус на поддержке 1С для малого бизнеса",
        }
    )
    print(demo)