import os
import json
import time
from typing import List, Dict
from openai import OpenAI
import requests


def _get_config():
    """Read LLM config from environment variables at call time."""
    return {
        "url": os.environ.get("LLM_URL", ""),
        "api_key": os.environ.get("LLM_API_KEY", ""),
        "model": os.environ.get("LLM_MODEL", ""),
        "protocol": os.environ.get("LLM_PROTOCOL", "OPENAI_STYLE"),
    }


def call_llm_anthropic(
    system: str,
    messages: List[Dict[str, str]],
    max_tokens: int = 8000,
    max_retries: int = 5
) -> str:
    """Call the LLM API using streaming to avoid proxy timeout."""
    cfg = _get_config()
    headers = {
        "Content-Type": "application/json",
        "x-api-key": cfg["api_key"],
        "anthropic-version": "2023-06-01"
    }
    data = {
        "model": cfg["model"],
        "max_tokens": max_tokens,
        "system": [{"type": "text", "text": system}],
        "messages": messages,
        "stream": True
    }
    for attempt in range(max_retries):
        try:
            response = requests.post(
                cfg["url"] + "/messages",
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
                wait = min(wait, 60)
                print(f"[LLM] Attempt {attempt + 1} failed: {e}. Retrying in {wait}s...")
                time.sleep(wait)
            else:
                return f"Error: {str(e)}"

def call_llm_openai(
    system: str,
    messages: List[Dict[str, str]],
    max_tokens: int = 8000,
    max_retries: int = 5,
    temperature: float = 1.0,
    top_p: float = 0.95
) -> str:
    cfg = _get_config()
    client = OpenAI(api_key=cfg["api_key"], base_url=cfg["url"])
    all_messages = []
    if system:
        all_messages.append({"role": "system", "content": system})
    all_messages.extend(messages)

    for attempt in range(max_retries):
        try:
            response = client.chat.completions.create(
                model=cfg["model"],
                max_tokens=max_tokens,
                temperature=temperature,
                top_p=top_p,
                messages=all_messages
            )
            return response.choices[0].message.content
        except Exception as e:
            if attempt < max_retries - 1:
                wait = 2 ** attempt
                wait = min(wait, 60)
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
    cfg = _get_config()
    if cfg["protocol"] == "OPENAI_STYLE":
        return call_llm_openai(system, messages, max_tokens, max_retries)
    elif cfg["protocol"] == "ANTHROPIC_STYLE":
        return call_llm_anthropic(system, messages, max_tokens, max_retries)
    else:
        raise ValueError(f"Unsupported protocol: {cfg['protocol']}")
