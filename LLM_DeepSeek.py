from __future__ import annotations

from openai import OpenAI

from config import API_KEY

API_URL = "https://llmapi.paratera.com"
BASE_URL = f"{API_URL}/v1/"

client = OpenAI(
    api_key=API_KEY,
    base_url=BASE_URL,
)

MODEL_FLASH = "DeepSeek-V4-Flash"
MODEL_PRO = "DeepSeek-V4-Pro"


def chat(messages: list[dict[str, str]], model: str) -> dict:
    """Centralized chat completion entrypoint for the whole project."""
    return client.chat.completions.create(messages=messages, model=model).model_dump()


def extract_text(response: dict) -> str:
    choices = response.get("choices", [])
    if not choices:
        raise ValueError("API response does not contain choices.")

    message = choices[0].get("message", {})
    content = message.get("content", "")
    if isinstance(content, list):
        text_parts = [item.get("text", "") for item in content if item.get("type") == "text"]
        return "".join(text_parts).strip()
    return str(content).strip()


def chat_text_flash(messages: list[dict[str, str]], model=MODEL_FLASH) -> str:
    response = chat(messages=messages, model=model)
    return extract_text(response)

def chat_text_pro(messages: list[dict[str, str]], model=MODEL_PRO) -> str:
    response = chat(messages=messages, model=model)
    return extract_text(response)

def chat_text_flash_with_usage(messages: list[dict[str, str]], model=MODEL_FLASH) -> tuple[str, dict]:
    response = chat(messages=messages, model=model)
    return extract_text(response), response.get("usage") or {}

def chat_text_pro_with_usage(messages: list[dict[str, str]], model=MODEL_PRO) -> tuple[str, dict]:
    response = chat(messages=messages, model=model)
    return extract_text(response), response.get("usage") or {}


if __name__ == "__main__":
    demo_messages = [
        {
            "role": "system",
            "content": "You are a helpful assistant.",
        },
        {
            "role": "user",
            "content": "What are some famous landmarks in Rome?",
        },
    ]

    print(chat_text_flash(demo_messages))
