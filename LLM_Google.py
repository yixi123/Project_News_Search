from __future__ import annotations
import hashlib
import json
import os
import re
import time
from datetime import datetime

from google import genai
from google.genai import types
from config import API_KEY_GOOGLE
from prompt import generate_bouncer_prompt, generate_full_prompt

client = genai.Client(api_key=API_KEY_GOOGLE)

MODEL_GOOGLE = "gemini-3.5-flash"
MODEL_BOUNCER = "gemini-3.5-flash"
TEMPERATURE_DEFAULT = 0.1
MAX_TOKENS_DEFAULT = 8192
LOG_DIR = "logs_google"
os.makedirs(LOG_DIR, exist_ok=True)

def parse_messages(messages: list[dict[str, str]]) -> tuple[list[types.Content], str]:
    contents = []
    system_instruction = ""
    for m in messages:
        if m["role"] == "system":
            system_instruction = m["content"]
        elif m["role"] == "user":
            contents.append(types.Content(role="user", parts=[types.Part.from_text(text=m["content"])]))
        elif m["role"] == "assistant":
            contents.append(types.Content(role="model", parts=[types.Part.from_text(text=m["content"])]))
    return contents, system_instruction

def chat(
    messages: list[dict[str, str]],
    model: str = MODEL_GOOGLE,
    thinking: dict | None = None,
    stream: bool = False,
    max_tokens: int = MAX_TOKENS_DEFAULT,
    temperature: float = TEMPERATURE_DEFAULT,
):
    """Centralized chat completion entrypoint for Google models."""
    contents, system_instruction = parse_messages(messages)
    config_args = {
        "temperature": temperature,
        "max_output_tokens": max_tokens
    }
    if system_instruction:
        config_args["system_instruction"] = system_instruction
        
    config = types.GenerateContentConfig(**config_args)
    if stream:
        return client.models.generate_content_stream(model=model, contents=contents, config=config)
    return client.models.generate_content(model=model, contents=contents, config=config)

def stream_parsed_events(response_stream, start_time, messages, kwargs, log_file_name="llm_stream_output", log_file_dir=LOG_DIR):
    buffer = ""
    in_timeline_array = False
    brace_count = 0
    in_string = False
    escape_next = False
    current_event_str = ""
    
    content_log_path = os.path.join(log_file_dir, f"{log_file_name}_content.txt")
    meta_log_path = os.path.join(log_file_dir, f"{log_file_name}_meta.json")
    content_log_file = open(content_log_path, "w", encoding="utf-8")
    
    system_prompt = next((m["content"] for m in messages if m["role"] == "system"), "")
    user_prompt = next((m["content"] for m in messages if m["role"] == "user"), "")
    
    content_log_file.write(f"=== System Prompt ===\n{system_prompt}\n\n")
    content_log_file.write(f"=== Prompt/Input ===\n{user_prompt}\n\n")
    content_log_file.write(f"=== Hyperparameters ===\n{json.dumps(kwargs, indent=2)}\n\n")
    content_log_file.write("=== Completion/Output ===\n")

    first_token_time = None
    finish_reason = None
    collected_timeline = []
    final_usage = None
    
    try:
        for chunk in response_stream:
            if first_token_time is None:
                first_token_time = time.time()
                
            if hasattr(chunk, "usage_metadata") and chunk.usage_metadata:
                final_usage = chunk.usage_metadata
            
            if hasattr(chunk, "candidates") and chunk.candidates and getattr(chunk.candidates[0], "finish_reason", None):
                finish_reason = getattr(getattr(chunk.candidates[0], "finish_reason"), "name", str(chunk.candidates[0].finish_reason))

            content = chunk.text if hasattr(chunk, "text") else ""
            if not content:
                continue

            content_log_file.write(content)
            content_log_file.flush()
            buffer += content

            if not in_timeline_array:
                match_idx = buffer.find('"key_events":')
                if match_idx != -1:
                    bracket_idx = buffer.find('[', match_idx)
                    if bracket_idx != -1:
                        in_timeline_array = True
                        buffer = buffer[bracket_idx + 1:]
                
            if not in_timeline_array:
                continue

            for char in buffer:
                if escape_next:
                    escape_next = False
                elif char == '\\':
                    escape_next = True
                elif char == '"':
                    in_string = not in_string

                if not in_string:
                    if char == '{':
                        if brace_count == 0:
                            current_event_str = ""
                        brace_count += 1
                    elif char == '}':
                        brace_count -= 1

                if brace_count > 0 or (brace_count == 0 and char == '}'):
                    current_event_str += char

                if brace_count == 0 and current_event_str.strip():
                    try:
                        event_dict = json.loads(current_event_str)
                        collected_timeline.append(event_dict)
                        yield event_dict
                    except json.JSONDecodeError as e:
                        print(f"Warning: Incremental parse failed on chunk: {e}")
                    current_event_str = ""
            buffer = ""
            
    finally:
        end_time = time.time()
        ttft = first_token_time - start_time if first_token_time else 0
        total_latency = end_time - start_time
        
        prompt_tokens = final_usage.prompt_token_count if final_usage and hasattr(final_usage, "prompt_token_count") else 0
        completion_tokens = final_usage.candidates_token_count if final_usage and hasattr(final_usage, "candidates_token_count") else 0
        total_tokens = final_usage.total_token_count if final_usage and hasattr(final_usage, "total_token_count") else 0
        tps = completion_tokens / total_latency if total_latency > 0 else 0
        
        meta = {
            "Timestamp": {
                "start_time": datetime.fromtimestamp(start_time).isoformat(),
                "completion_time": datetime.fromtimestamp(end_time).isoformat()
            },
            "Userinfo": "local_script_execution",
            "Prompt Tokens": prompt_tokens,
            "Completion Tokens": completion_tokens,
            "Total Tokens": total_tokens,
            "Cost": 0,
            "Time to First Token (TTFT)": ttft,
            "Tokens Per Second (TPS)": tps,
            "Total Latency": total_latency,
            "Finish Reason": finish_reason
        }
        with open(meta_log_path, "w", encoding="utf-8") as f:
            json.dump(meta, f, indent=2)
            
        parsed_output_path = os.path.join(log_file_dir, f"{log_file_name}_parsed.json")
        with open(parsed_output_path, "w", encoding="utf-8") as f:
            json.dump({"key_events": collected_timeline}, f, indent=2)
            
        content_log_file.close()
        
        if finish_reason == "SAFETY" or finish_reason == "BLOCKLIST":
            yield {"type": "sensitive", "message": "Sensitive content detected"}

def stream_chat_google(
    messages: list[dict[str, str]],
    model: str = MODEL_GOOGLE,
    thinking: dict | None = None,
    max_tokens: int = MAX_TOKENS_DEFAULT,
    temperature: float = TEMPERATURE_DEFAULT,
):
    return chat(messages=messages, model=model, thinking=thinking, stream=True, max_tokens=max_tokens, temperature=temperature)

def google_preset_chat(messages: list) -> dict:
    message_hash = hashlib.md5(json.dumps(messages, sort_keys=True).encode("utf-8")).hexdigest()
    print(f"Messages hash: {message_hash}")
    if os.path.exists(f"{LOG_DIR}/{message_hash}_parsed.json"):
        print("Parsed output already exists for these messages. Loading from file...")
        def generater():
            with open(f"{LOG_DIR}/{message_hash}_parsed.json", "r", encoding="utf-8") as f:
                parsed_data = json.load(f)
                time.sleep(3)
                for event in parsed_data.get("key_events", []):
                    yield event
            meta_path = f"{LOG_DIR}/{message_hash}_meta.json"
            if os.path.exists(meta_path):
                with open(meta_path, "r", encoding="utf-8") as meta_f:
                    meta_data = json.load(meta_f)
                    if meta_data.get("Finish Reason") in ["SAFETY", "BLOCKLIST"]:
                        yield {"type": "sensitive", "message": "Sensitive content detected"}
        return generater()
    else: 
        start_time = time.time()
        raw_stream = stream_chat_google(messages)
        kwargs = {"model": MODEL_GOOGLE, "max_tokens": MAX_TOKENS_DEFAULT, "temperature": TEMPERATURE_DEFAULT}
        return stream_parsed_events(raw_stream, start_time, messages, kwargs, log_file_name=message_hash)

def get_rejection_message(error_code: str, corrected_query: str | None = None) -> str:
    messages = {
        "GIBBERISH": "I didn't quite catch that. Please search for a specific news topic, company, or event.",
        "CONVERSATIONAL": "I'm a timeline generator, not a chatbot! Please enter a specific news event you'd like to explore.",
        "INJECTION": "Invalid search query detected. Please search for a standard news topic.",
        "OUT_OF_BOUNDS": "My database currently only covers events between 2016 and 2026. Please search for a more recent topic!",
        "INVALID_EVENT": "I can only generate timelines for news events, public figures, or companies. Try searching for something like 'SpaceX' or 'OpenAI'.",
        "MISSPELL": f"Did you mean '{corrected_query}'?"
    }
    return messages.get(error_code, "Please search for a specific, modern news event.")

def bouncer_preset_chat(user_query: str) -> dict:
    start_time = time.time()
    bouncer_messages = generate_bouncer_prompt(user_query)
    bouncer_data = {}
    bouncer_json_path = os.path.join(LOG_DIR, "bouncer.json")
    bouncer_log_path = os.path.join(LOG_DIR, "bouncer_log.jsonl")

    if os.path.exists(bouncer_json_path):
        with open(bouncer_json_path, "r", encoding="utf-8") as f:
            bouncer_data = json.load(f)

    if user_query in bouncer_data:
        time.sleep(1.5)
        bouncer_data[user_query]["rejection_reason"] = get_rejection_message(bouncer_data[user_query].get("error_code", ""), corrected_query=bouncer_data[user_query].get("corrected_query", None))
        return bouncer_data[user_query]

    response = chat(messages=bouncer_messages, model=MODEL_BOUNCER, stream=False, max_tokens=2048, temperature=0.0)

    try:
        content = response.text if hasattr(response, "text") else ""
        code_block_match = re.search(r"```json\s*(\{.*\})\s*```", content, re.DOTALL)
        if code_block_match:
            content = code_block_match.group(1)
        response_dict = json.loads(content)
    except (json.JSONDecodeError, IndexError) as e:
        print(f"Error parsing bouncer response: {e}")
        response_dict = {"is_valid": False, "error_code": "UNKNOWN"}

    bouncer_data[user_query] = response_dict
    with open(bouncer_json_path, "w", encoding="utf-8") as f:
        json.dump(bouncer_data, f, indent=2)

    end_time = time.time()
    total_latency = end_time - start_time
    ttft = total_latency
    final_usage = getattr(response, "usage_metadata", None)
    prompt_tokens = final_usage.prompt_token_count if final_usage and hasattr(final_usage, "prompt_token_count") else 0
    completion_tokens = final_usage.candidates_token_count if final_usage and hasattr(final_usage, "candidates_token_count") else 0
    total_tokens = final_usage.total_token_count if final_usage and hasattr(final_usage, "total_token_count") else 0
    tps = completion_tokens / total_latency if total_latency > 0 else 0
    finish_reason = getattr(getattr(response.candidates[0], "finish_reason", None), "name", str(response.candidates[0].finish_reason)) if hasattr(response, "candidates") and response.candidates else ""

    log_entry = {
        "query": user_query,
        "Timestamp": {
            "start_time": datetime.fromtimestamp(start_time).isoformat(),
            "completion_time": datetime.fromtimestamp(end_time).isoformat()
        },
        "Userinfo": "local_script_execution",
        "Prompt Tokens": prompt_tokens,
        "Completion Tokens": completion_tokens,
        "Total Tokens": total_tokens,
        "Cost": 0,
        "Time to First Token (TTFT)": ttft,
        "Tokens Per Second (TPS)": tps,
        "Total Latency": total_latency,
        "Finish Reason": finish_reason
    }

    with open(bouncer_log_path, "a", encoding="utf-8") as handle:
        handle.write(json.dumps(log_entry, ensure_ascii=False, indent=2) + "\n")
    response_dict["rejection_reason"] = get_rejection_message(response_dict.get("error_code", ""), corrected_query=response_dict.get("corrected_query", None))
    return response_dict

if __name__ == "__main__":
    from retriever import get_articles_from_query
    demo_query = "aweasdnoisahoixzhcvrw"
    print("Generating timeline for query:", demo_query)
    print("Retrieving articles...")
    returned_articles = get_articles_from_query(demo_query)
    demo_messages = generate_full_prompt(demo_query, returned_articles)

    print("Generating timeline...\n")
    event_generator = google_preset_chat(demo_messages)
    event_count = 1
    for event in event_generator:
        print(f"--- EVENT {event_count} READY ---")
        print(json.dumps(event, indent=2))
        print("-" * 25 + "\n")
        event_count += 1
