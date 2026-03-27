import os
import json
import time
from typing import List, Dict
from openai import OpenAI
import requests
from dotenv import load_dotenv

load_dotenv()

model_choice = "minimax"

# Configuration
LLM_URL_CLAUDE = os.getenv("LLM_URL_CLAUDE")
LLM_API_KEY_CLAUDE = os.getenv("LLM_API_KEY_CLAUDE")
LLM_MODEL_CLAUDE = os.getenv("LLM_MODEL_CLAUDE", "claude-opus-4-6")

LLM_URL_MINIMAX = os.getenv("LLM_URL_MINIMAX")
LLM_API_KEY_MINIMAX = os.getenv("LLM_API_KEY_MINIMAX")
LLM_MODEL_MINIMAX = os.getenv("LLM_MODEL_MINIMAX", "MiniMax-M2.7")

client_claude = OpenAI(
    api_key=LLM_API_KEY_CLAUDE,
    base_url=LLM_URL_CLAUDE
)

client_minimax = OpenAI(
    api_key=LLM_API_KEY_MINIMAX,
    base_url=LLM_URL_MINIMAX
)

def call_llm_claude(
    system: str,
    messages: List[Dict[str, str]],
    max_tokens: int = 8000,
    max_retries: int = 5
) -> str:
    """Call the LLM API using streaming to avoid proxy timeout."""
    headers = {
        "Content-Type": "application/json",
        "x-api-key": LLM_API_KEY_CLAUDE,
        "anthropic-version": "2023-06-01"
    }
    data = {
        "model": LLM_MODEL_CLAUDE,
        "max_tokens": max_tokens,
        "system": [{"type": "text", "text": system}],
        "messages": messages,
        "stream": True
    }
    for attempt in range(max_retries):
        try:
            response = requests.post(
                LLM_URL_CLAUDE + "/messages",
                headers=headers,
                json=data,
                timeout=60,
                stream=True
            )
            response.raise_for_status()
            response.encoding = "utf-8"

            full_text = ""
            for line in response.iter_lines(decode_unicode=True):
                if not line or not line.startswith("data: "):
                    continue
                payload = line[len("data: "):]
                if payload.strip() == "[DONE]":
                    break
                try:
                    event = json.loads(payload)
                except json.JSONDecodeError:
                    continue
                event_type = event.get("type", "")
                if event_type == "content_block_delta":
                    delta = event.get("delta", {})
                    if delta.get("type") == "text_delta":
                        full_text += delta.get("text", "")
                elif event_type == "message_stop":
                    break

            if full_text:
                return full_text
            else:
                raise Exception("Empty response from streaming API")
        except Exception as e:
            if attempt < max_retries - 1:
                wait = 2 ** attempt
                wait = min(wait, 60)  # Cap the wait time to avoid excessively long delays
                print(f"[LLM] Attempt {attempt + 1} failed: {e}. Retrying in {wait}s...")
                time.sleep(wait)
            else:
                return f"Error: {str(e)}"

def call_llm_minimax(
    system: str,
    messages: List[Dict[str, str]],
    max_tokens: int = 8000,
    max_retries: int = 5,
    temperature: float = 1.0,
    top_p: float = 0.95
) -> str:
    all_messages = []
    if system:
        all_messages.append({"role": "system", "content": system})
    all_messages.extend(messages)

    for attempt in range(max_retries):
        try:
            response = client_minimax.chat.completions.create(
                model=LLM_MODEL_MINIMAX,
                max_tokens=max_tokens,
                temperature=temperature,
                top_p=top_p,
                messages=all_messages
            )
            return response.choices[0].message.content
        except Exception as e:
            if attempt < max_retries - 1:
                wait = 2 ** attempt
                wait = min(wait, 60)  # Cap the wait time to avoid excessively long delays
                print(f"[LLM] Attempt {attempt + 1} failed: {e}. Retrying in {wait}s...")
                time.sleep(wait)
            else:
                return f"Error: {str(e)}"
           
def call_llm(
    system: str,
    messages: List[Dict[str, str]],
    max_tokens: int = 100000,
    max_retries: int = 600
) -> str:
    if model_choice == "minimax":
        return call_llm_minimax(system, messages, max_tokens, max_retries)
    elif model_choice == "claude":
        return call_llm_claude(system, messages, max_tokens, max_retries)
    else:
        raise ValueError(f"Unsupported model choice: {model_choice}")