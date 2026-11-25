"""One bounded request per explicit action, with no SDK credential discovery."""

import json
import re
from dataclasses import dataclass

import httpx

from radar.config import validate_ollama
from radar.network import NetworkFailure, read_response

DEFAULT_MODELS = {
    "OpenAI": "gpt-4.1-mini",
    "Anthropic": "claude-sonnet-4-6",
    "Gemini": "gemini-3.5-flash-lite",
    "Ollama": "",
}
MAX_OUTPUT = 3500


class ProviderError(Exception):
    pass


@dataclass
class Completion:
    text: str
    usage: dict[str, int]


def complete(
    provider: str,
    model: str,
    key: str | None,
    system: str,
    prompt: str,
    *,
    ollama_url: str | None = None,
    test: bool = False,
    transport: httpx.BaseTransport | None = None,
) -> Completion:
    if provider not in DEFAULT_MODELS:
        raise ProviderError("Choose a supported provider.")
    if provider != "Ollama" and not key:
        raise ProviderError("Enter your own API key for the selected provider.")
    if key and (not re.fullmatch(r"[A-Za-z0-9._~-]{1,512}", key)):
        raise ProviderError("The API key contains invalid characters or has an invalid length.")
    if key and any(key in field for field in (system, prompt, model)):
        raise ProviderError("Remove the credential from the model name or briefing inputs.")
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:/-]{0,119}", model):
        raise ProviderError("Enter a valid model identifier.")
    if provider == "Gemini" and not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,119}", model):
        raise ProviderError("Use a bare Gemini model identifier.")
    tokens = 32 if test else MAX_OUTPUT
    messages = [{"role": "system", "content": system}, {"role": "user", "content": prompt}]
    headers = {}
    if provider == "OpenAI":
        url = "https://api.openai.com/v1/chat/completions"
        headers["Authorization"] = f"Bearer {key}"
        body = {"model": model, "messages": messages, "max_completion_tokens": tokens}
        if not test:
            body["response_format"] = {"type": "json_object"}
    elif provider == "Anthropic":
        url = "https://api.anthropic.com/v1/messages"
        headers = {"x-api-key": key, "anthropic-version": "2023-06-01"}
        body = {"model": model, "system": system, "messages": messages[1:], "max_tokens": tokens}
    elif provider == "Gemini":
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
        headers["x-goog-api-key"] = key
        generation = {"maxOutputTokens": tokens}
        if not test:
            generation["responseMimeType"] = "application/json"
        if model.startswith("gemini-2.5-flash"):
            generation["thinkingConfig"] = {"thinkingBudget": 0}
        body = {
            "systemInstruction": {"parts": [{"text": system}]},
            "contents": [{"role": "user", "parts": [{"text": prompt}]}],
            "generationConfig": generation,
        }
    else:
        if not ollama_url:
            raise ProviderError("Ollama is unavailable in this deployment.")
        url = f"{validate_ollama(ollama_url)}/api/chat"
        body = {
            "model": model,
            "messages": messages,
            "stream": True,
            "options": {"num_predict": tokens, "num_ctx": 8192},
        }
        if not test:
            body["format"] = "json"
    try:
        # Use the platform's HTTPS proxy when configured. Local Ollama bypasses it.
        with httpx.Client(trust_env=provider != "Ollama", transport=transport) as client:
            raw = read_response(
                client,
                "POST",
                url,
                limit=320_000,
                seconds=60,
                read_seconds=20,
                headers=headers,
                json=body,
            )
        result = decode(provider, raw)
        if key and key in result.text:
            raise ProviderError(
                "The provider returned sensitive content. The response was discarded."
            )
        return result
    except NetworkFailure as err:
        raise ProviderError(str(err)) from None
    except (ValueError, TypeError, KeyError, IndexError, AttributeError):
        raise ProviderError(
            "The provider returned an unreadable, refused, or incomplete response."
        ) from None


def decode(provider: str, raw: bytes) -> Completion:
    if provider == "Ollama":
        frames = [json.loads(line) for line in raw.splitlines()]
        end = frames[-1]
        if (
            not end["done"]
            or end.get("done_reason") == "length"
            or any("error" in f for f in frames)
        ):
            raise ValueError
        text = "".join(frame.get("message", {}).get("content", "") for frame in frames)
        usage = {"input": end.get("prompt_eval_count"), "output": end.get("eval_count")}
    else:
        data = json.loads(raw)
        if provider == "OpenAI":
            choice = data["choices"][0]
            if choice["finish_reason"] != "stop" or choice["message"].get("refusal"):
                raise ValueError
            text = choice["message"]["content"]
            usage = {
                "input": data.get("usage", {}).get("prompt_tokens"),
                "output": data.get("usage", {}).get("completion_tokens"),
            }
        elif provider == "Anthropic":
            if data["stop_reason"] not in {"end_turn", "stop_sequence"}:
                raise ValueError
            text = "".join(block["text"] for block in data["content"] if block["type"] == "text")
            usage = {
                "input": data.get("usage", {}).get("input_tokens"),
                "output": data.get("usage", {}).get("output_tokens"),
            }
        else:
            candidate = data["candidates"][0]
            if candidate["finishReason"] != "STOP":
                raise ValueError
            text = "".join(
                part.get("text", "")
                for part in candidate["content"]["parts"]
                if not part.get("thought")
            )
            usage = {
                "input": data.get("usageMetadata", {}).get("promptTokenCount"),
                "output": data.get("usageMetadata", {}).get("candidatesTokenCount"),
                "thinking": data.get("usageMetadata", {}).get("thoughtsTokenCount"),
            }
    if not isinstance(text, str) or not text.strip():
        raise ValueError
    return Completion(text, {name: value for name, value in usage.items() if type(value) is int})
