from __future__ import annotations

from zai import ZhipuAiClient
from config import API_KEY_GLM

client = ZhipuAiClient(api_key=API_KEY_GLM)

MODEL_GLM = "glm-5"

# System prompt for timeline generation
TIMELINE_SYSTEM_PROMPT = """You are an expert news editor and data structurer for a timeline generation system. Your task is to analyze a list of retrieved news articles, cluster similar stories, and output a chronological timeline strictly in JSON format.

RULES FOR THE TIMELINE:
1. Relevance Scoring (Importance 1-10): Assign an 'importance' score to each event strictly based on how directly it answers the user's specific query. 10 is a direct, major answer; 1 is tangential or minor context.
2. Clustering: If multiple articles describe the exact same event, merge them into a single timeline item. Combine their URLs into the 'sources' array. Do NOT create duplicate main events.
3. Hierarchy (Sub-events): If an article represents a minor follow-up, reaction, or sub-plot directly related to a major event, place it inside the 'sub_events' array of that parent event.
4. Output Format: You must respond ONLY with valid JSON matching the provided schema. Do not include markdown formatting like ```json or any conversational text.

REQUIRED JSON SCHEMA:
{
  "timeline": [
    {
      "date": "YYYY-MM-DD",
      "headline": "Clear, concise summary of the clustered event",
      "summary": "A detailed synthesis of the information from the clustered articles.",
      "importance": <int 1-10>,
      "sources": ["url1", "url2", ...],
      "sub_events": [
        {
          "date": "YYYY-MM-DD",
          "headline": "Sub-event headline",
          "summary": "Brief summary of this follow-up or related detail.",
          "importance": <int 1-10>,
          "sources": ["url3"]
        }
      ]
    }
  ]
}"""


def chat(
    messages: list[dict[str, str]],
    model: str = MODEL_GLM,
    thinking: dict | None = None,
    stream: bool = False,
    max_tokens: int = 65536,
    temperature: float = 1.0,
) -> dict:
    """Centralized chat completion entrypoint for GLM models."""
    return client.chat.completions.create(
        model=model,
        messages=messages,
        thinking=thinking or {"type": "enabled"},
        stream=stream,
        max_tokens=max_tokens,
        temperature=temperature,
    )


def extract_text(response: dict) -> str:
    """Extract text content from GLM API response."""
    choices = response.get("choices", [])
    if not choices:
        raise ValueError("API response does not contain choices.")

    message = choices[0].get("message", {})
    content = message.get("content", "")
    if isinstance(content, list):
        text_parts = [item.get("text", "") for item in content if item.get("type") == "text"]
        return "".join(text_parts).strip()
    return str(content).strip()


def chat_text_glm(
    messages: list[dict[str, str]],
    model: str = MODEL_GLM,
    thinking: dict | None = None,
    max_tokens: int = 65536,
    temperature: float = 1.0,
) -> str:
    """Non-streaming chat with GLM, returns text response."""
    response = chat(
        messages=messages,
        model=model,
        thinking=thinking,
        stream=False,
        max_tokens=max_tokens,
        temperature=temperature,
    )
    return extract_text(response)


def chat_text_glm_with_usage(
    messages: list[dict[str, str]],
    model: str = MODEL_GLM,
    thinking: dict | None = None,
    max_tokens: int = 65536,
    temperature: float = 1.0,
) -> tuple[str, dict]:
    """Non-streaming chat with GLM, returns text response and usage statistics."""
    response = chat(
        messages=messages,
        model=model,
        thinking=thinking,
        stream=False,
        max_tokens=max_tokens,
        temperature=temperature,
    )
    return extract_text(response), response.get("usage", {})


def stream_chat_glm(
    messages: list[dict[str, str]],
    model: str = MODEL_GLM,
    thinking: dict | None = None,
    max_tokens: int = 65536,
    temperature: float = 1.0,
):
    """Streaming chat with GLM, yields chunks."""
    response = chat(
        messages=messages,
        model=model,
        thinking=thinking,
        stream=True,
        max_tokens=max_tokens,
        temperature=temperature,
    )
    return response


if __name__ == "__main__":
    # Demo: Generate timeline from news articles
    demo_messages = [
        {
            "role": "system",
            "content": TIMELINE_SYSTEM_PROMPT,
        },
        {
            "role": "user",
            "content": "Please generate a timeline based on the retrieved articles. I will provide the user's search query and the raw articles.",
        },
        {
            "role": "assistant",
            "content": "I understand the rules, the clustering logic, and the importance scoring criteria based on query relevance. Please provide the user's search query and the JSON array of retrieved articles, and I will return the strictly formatted JSON timeline.",
        },
        {
            "role": "user",
            "content": """USER QUERY: "The rise of LLMs and AI regulations in early 2023"

RETRIEVED ARTICLES:
[
  {"date": "2023-03-14", "title": "OpenAI announces GPT-4", "description": "The new multimodal model is here.", "url": "https://tech1.com/gpt4"},
  {"date": "2023-03-14", "title": "GPT-4 Released by OpenAI", "description": "OpenAI launches its most capable AI model to date.", "url": "https://news2.com/openai-gpt4"},
  {"date": "2023-03-15", "title": "Developers react to GPT-4 pricing", "description": "The API costs are causing a stir in the dev community.", "url": "https://dev3.com/gpt4-price"},
  {"date": "2023-03-22", "title": "Tech leaders call for AI Pause", "description": "Elon Musk and others sign an open letter to pause Giant AI Experiments.", "url": "https://worldnews.com/ai-pause"},
  {"date": "2023-03-22", "title": "Open letter demands 6-month halt on AI", "description": "Experts warn of profound risks to society.", "url": "https://ai-ethics.org/letter"}
]""",
        },
    ]

    # Stream the response
    response = stream_chat_glm(demo_messages)

    reasoning_started = False
    for chunk in response:
        if chunk.choices[0].delta.reasoning_content:
            if not reasoning_started:
                print("\n--- Reasoning ---\n")
                reasoning_started = True
            print(chunk.choices[0].delta.reasoning_content, end="", flush=True)

        if chunk.choices[0].delta.content:
            if reasoning_started:
                print("\n--- Final Answer ---\n")
                reasoning_started = False
            print(chunk.choices[0].delta.content, end="", flush=True)