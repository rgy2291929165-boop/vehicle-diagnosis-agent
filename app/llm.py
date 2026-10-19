import os
from pathlib import Path
from typing import Dict, List

import httpx
from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(PROJECT_ROOT / ".env")

DEFAULT_BASE_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1"
DEFAULT_MODEL = "qwen3.7-flash"
ANSWER_PROMPT_VERSION = "week2-answer-v4"

class ModelConfigurationError(Exception):
    pass


class ModelTimeoutError(Exception):
    pass


class ModelEmptyResponseError(Exception):
    pass


class ModelRequestError(Exception):
    pass


def build_messages(question: str, contexts: List[Dict]) -> List[Dict]:
    context_text = "\n\n".join(
        (
            f'[资料 {index}]\n'
            f'来源: {context["source"]}\n'
            f'片段 ID: {context["chunk_id"]}\n'
            f'内容: {context["text"]}'
        )
        for index, context in enumerate(contexts, start=1)
    )
    return [
        {
            "role": "system",
            "content": (
                "你是新能源汽车故障诊断助手。"
                "只能依据提供的资料片段回答，不要补充资料中不存在的事实。"
                "只要任一资料片段能直接支持问题所需的安全、具体结论，就应给出简洁回答；"
                "不要因为问题措辞与资料不完全相同而拒答。"
                "只回答问题直接要求的结论，不要附加资料没有明确说明的原因、预防措施或维修建议。"
                "每项关键结论紧邻附上对应的 [来源: document_id:chunk_index]，"
                "例如 [来源: w2-tesla-cold-weather:0]；不要添加“片段 ID:”等额外文字。"
                "若相邻资料片段内容重叠，而其中一个片段开头明显截断，"
                "必须引用包含完整句子和完整设置名称的片段。"
                "仅当所有资料片段都不能直接支持回答时，必须且只能输出 NO_EVIDENCE。"
            ),
        },
        {
            "role": "user",
            "content": f"资料片段：\n{context_text}\n\n用户问题：{question}",
        },
    ]


def generate_answer(question: str, contexts: List[Dict]) -> str:
    api_key = os.getenv("DASHSCOPE_API_KEY")

    if not api_key:
        raise ModelConfigurationError("未配置 DASHSCOPE_API_KEY")

    base_url = os.getenv("DASHSCOPE_BASE_URL", DEFAULT_BASE_URL).rstrip("/")
    model = os.getenv("DASHSCOPE_MODEL", DEFAULT_MODEL)
    payload = {
        "model": model,
        "temperature": 0.2,
        "enable_thinking": False,
        "max_tokens": 512,
        "messages": build_messages(question, contexts),
    }

    try:
        response = httpx.post(
            f"{base_url}/chat/completions",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json=payload,
            timeout=20.0,
        )
        response.raise_for_status()
    except httpx.TimeoutException as error:
        raise ModelTimeoutError("模型响应超时") from error
    except httpx.HTTPStatusError as error:
        print(
        "DashScope 请求失败：",
        error.response.status_code,
        error.response.text[:500],
    )
        raise ModelRequestError("模型服务返回错误状态") from error
    except httpx.HTTPError as error:
        raise ModelRequestError("模型服务请求失败") from error

    try:
        content = response.json()["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError, ValueError) as error:
        raise ModelEmptyResponseError("模型未返回可用内容") from error

    if not isinstance(content, str) or not content.strip():
        raise ModelEmptyResponseError("模型返回了空内容")

    return content.strip()
