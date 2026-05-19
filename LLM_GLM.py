from __future__ import annotations
import hashlib
import json
import os
import re
import time
from datetime import datetime

from zai import ZhipuAiClient
from config import API_KEY_GLM
from prompt import generate_bouncer_prompt, generate_full_prompt

client = ZhipuAiClient(api_key=API_KEY_GLM)

MODEL_GLM = "glm-4.5-air"
MODEL_BOUNCER = "glm-4.5-air"
TEMPERATURE_DEFAULT = 0.1
MAX_TOKENS_DEFAULT = 65536
THINKING_DEFAULT = {"type": "disabled"}
LOG_DIR = "logs_glm"
os.makedirs(LOG_DIR, exist_ok=True)


def chat(
    messages: list[dict[str, str]],
    model: str = MODEL_GLM,
    thinking: dict | None = None,
    stream: bool = False,
    max_tokens: int = MAX_TOKENS_DEFAULT,
    temperature: float = TEMPERATURE_DEFAULT,
) -> dict:
    """Centralized chat completion entrypoint for GLM models."""
    return client.chat.completions.create(
        model=model,
        messages=messages,
        thinking=thinking or THINKING_DEFAULT,
        stream=stream,
        max_tokens=max_tokens,
        temperature=temperature,
    )



def stream_parsed_events(response_stream, start_time, messages, kwargs, log_file_name="llm_stream_output", log_file_dir=LOG_DIR):
    """
    Consumes the LLM token stream, extracts individual timeline events safely 
    from within the `"timeline": [...]` array, and yields them.
    Also logs content and metadata to separate files.
    """
    buffer = ""
    in_timeline_array = False
    
    # State tracking
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

    try:
        final_usage = None
        for chunk in response_stream:
            if first_token_time is None:
                first_token_time = time.time()
                
            if hasattr(chunk, 'usage') and chunk.usage:
                final_usage = chunk.usage

            if not getattr(chunk, 'choices', None) or len(chunk.choices) == 0:
                continue
                
            if hasattr(chunk.choices[0], 'finish_reason') and chunk.choices[0].finish_reason:
                finish_reason = chunk.choices[0].finish_reason

            content = chunk.choices[0].delta.content
            if not content:
                continue

            content_log_file.write(content)
            content_log_file.flush()

            buffer += content

            # Step 1: Wait until we get past the root object and into the array
            if not in_timeline_array:
                match_idx = buffer.find('"key_events":')
                if match_idx != -1:
                    bracket_idx = buffer.find('[', match_idx)
                    if bracket_idx != -1:
                        in_timeline_array = True
                        # Slice the buffer to start right after the '['
                        buffer = buffer[bracket_idx + 1:]
                
            if not in_timeline_array:
                continue

            # Step 2: We are inside the array. Parse the characters safely.
            for char in buffer:
                # Handle string state so we don't count braces inside quotes
                if escape_next:
                    escape_next = False
                elif char == '\\':
                    escape_next = True
                elif char == '"':
                    in_string = not in_string

                # If we are NOT inside a string, track the braces
                if not in_string:
                    if char == '{':
                        if brace_count == 0:
                            # Starting a new event object
                            current_event_str = ""
                        brace_count += 1
                    elif char == '}':
                        brace_count -= 1

                # If we are currently building an object, record the character
                if brace_count > 0 or (brace_count == 0 and char == '}'):
                    current_event_str += char

                # If brace_count hits 0 after we started recording, the object is complete!
                if brace_count == 0 and current_event_str.strip():
                    try:
                        event_dict = json.loads(current_event_str)
                        collected_timeline.append(event_dict)
                        yield event_dict
                    except json.JSONDecodeError as e:
                        print(f"Warning: Incremental parse failed on chunk: {e}")

                    # Reset for the next event
                    current_event_str = ""

            # Clear the buffer after processing its characters to save memory
            buffer = ""
    finally:
        end_time = time.time()
        ttft = first_token_time - start_time if first_token_time else 0
        total_latency = end_time - start_time
        
        prompt_tokens = final_usage.prompt_tokens if hasattr(final_usage, "prompt_tokens") else 0
        completion_tokens = final_usage.completion_tokens if hasattr(final_usage, "completion_tokens") else 0
        total_tokens = final_usage.total_tokens if hasattr(final_usage, "total_tokens") else 0
        
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
            "Cost": 0, # Add actual parsing for cost if applicable
            "Time to First Token (TTFT)": ttft,
            "Tokens Per Second (TPS)": tps,
            "Total Latency": total_latency,
            "Finish Reason": finish_reason
        }
        with open(meta_log_path, "w", encoding="utf-8") as f:
            json.dump(meta, f, indent=2)
            
        parsed_output_path = os.path.join(log_file_dir, f"{log_file_name}_parsed.json")
        with open(parsed_output_path, "w", encoding="utf-8") as f:
            json.dump({
                "key_events": collected_timeline
            }, f, indent=2)
            
        content_log_file.close()


def stream_chat_glm(
    messages: list[dict[str, str]],
    model: str = MODEL_GLM,
    thinking: dict | None = None,
    max_tokens: int = MAX_TOKENS_DEFAULT,
    temperature: float = TEMPERATURE_DEFAULT,
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


def glm_preset_chat(messages: list) -> dict:
    
    # hash the demo messages for logging
    message_hash = hashlib.md5(json.dumps(messages, sort_keys=True).encode('utf-8')).hexdigest()
    print(f"Messages hash: {message_hash}")
    if os.path.exists(f"{LOG_DIR}/{message_hash}_parsed.json"):
        print("Parsed output already exists for these messages. Loading from file...")
        def generater():
            with open(f"{LOG_DIR}/{message_hash}_parsed.json", "r", encoding="utf-8") as f:
                parsed_data = json.load(f)
                time.sleep(3)  # Simulate some latency
                # Yield timeline events
                for event in parsed_data.get("timeline", []):
                    yield event
        return generater()
    else: 
        # 1. Start the raw LLM stream (ensure thinking is disabled for pure JSON speed)
        start_time = time.time()
        raw_stream = stream_chat_glm(messages)
    
        # 2. Pass the raw stream into our incremental parser
        kwargs = {
            "model": MODEL_GLM,
            "thinking": THINKING_DEFAULT,
            "max_tokens": MAX_TOKENS_DEFAULT,
            "temperature": TEMPERATURE_DEFAULT
        }
        event_generator = stream_parsed_events(raw_stream, start_time, messages, kwargs, log_file_name=message_hash)
        return event_generator


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

    # Load cached bouncer responses if present
    if os.path.exists(bouncer_json_path):
        with open(bouncer_json_path, "r", encoding="utf-8") as f:
            bouncer_data = json.load(f)

    # If cached, return cached response (do not log cached hits)
    if user_query in bouncer_data:
        time.sleep(1.5)  # Simulate some latency even for cached results
        bouncer_data[user_query]["rejection_reason"] = get_rejection_message(bouncer_data[user_query].get("error_code", ""), corrected_query=bouncer_data[user_query].get("corrected_query", None))
        return bouncer_data[user_query]

    # Not cached: call the model
    response = chat(
        messages=bouncer_messages,
        model=MODEL_BOUNCER,
        thinking=THINKING_DEFAULT,
        stream=False,
        max_tokens=2048,
        temperature=0.0,
    )

    # convert the response content (a JSON string) into a dict
    try:
        content = response.choices[0].message.content
        # clean the content ```json ... ``` if it is wrapped in a code block
        code_block_match = re.search(r"```json\s*(\{.*\})\s*```", content, re.DOTALL)
        if code_block_match:
            content = code_block_match.group(1)
        response_dict = json.loads(content)
    except (json.JSONDecodeError, IndexError) as e:
        print(content if 'content' in locals() else '')
        print(f"Error parsing bouncer response: {e}")
        response_dict = {
            "is_valid": False,
            "error_code": "UNKNOWN"
        }

    # Save the parsed bouncer response cache
    bouncer_data[user_query] = response_dict
    with open(bouncer_json_path, "w", encoding="utf-8") as f:
        json.dump(bouncer_data, f, indent=2)

    # Build and append log entry
    end_time = time.time()
    total_latency = end_time - start_time
    ttft = total_latency
    final_usage = getattr(response, "usage", None)
    prompt_tokens = getattr(final_usage, "prompt_tokens", 0) if final_usage else 0
    completion_tokens = getattr(final_usage, "completion_tokens", 0) if final_usage else 0
    total_tokens = getattr(final_usage, "total_tokens", 0) if final_usage else 0
    tps = completion_tokens / total_latency if total_latency > 0 else 0
    finish_reason = None
    try:
        finish_reason = response.choices[0].finish_reason
    except Exception:
        finish_reason = None

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
        "Finish Reason": finish_reason or ""
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

    event_generator = glm_preset_chat(demo_messages)
    # 3. Iterate over the yielded events
    event_count = 1
    for event in event_generator:
        print(f"--- EVENT {event_count} READY ---")
        print(json.dumps(event, indent=2))
        print("-" * 25 + "\n")
        event_count += 1

  