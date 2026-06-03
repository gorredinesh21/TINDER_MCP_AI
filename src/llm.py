"""
Pluggable LLM backend (LangChain). Two interchangeable options, chosen by the
LLM_BACKEND env var — NO Anthropic/Claude anywhere.

  LLM_BACKEND=hf       -> Hugging Face Inference API   (needs HUGGINGFACEHUB_API_TOKEN)
  LLM_BACKEND=ollama   -> local model via Ollama       (no token, runs on your machine)

Both resolve to a LangChain *chat* model, so coach.py is fully backend-agnostic:
`LLM.generate(system, user) -> str`.
"""
from __future__ import annotations

import os
import requests
from dataclasses import dataclass
from typing import Any


class GeminiLLM:
    def __init__(self, api_key: str, model: str, temperature: float, max_tokens: int):
        self.api_key = api_key
        self.model = model
        self.temperature = temperature
        self.max_tokens = max_tokens

    def invoke(self, messages: list) -> Any:
        system_messages = [m.content for m in messages if m.__class__.__name__ == "SystemMessage"]
        other_messages = [m for m in messages if m.__class__.__name__ != "SystemMessage"]
        
        system_instruction_payload = {}
        if system_messages:
            system_instruction_payload = {
                "system_instruction": {
                    "parts": [{"text": "\n".join(system_messages)}]
                }
            }
            
        contents_payload = []
        for msg in other_messages:
            role = "model" if msg.__class__.__name__ == "AIMessage" else "user"
            contents_payload.append({
                "role": role,
                "parts": [{"text": msg.content}]
            })
            
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{self.model}:generateContent?key={self.api_key}"
        payload = {
            "contents": contents_payload,
            "generationConfig": {
                "temperature": self.temperature,
                "maxOutputTokens": self.max_tokens,
            }
        }
        if system_instruction_payload:
            payload.update(system_instruction_payload)
            
        res = requests.post(url, json=payload, timeout=60)
        res.raise_for_status()
        data = res.json()
        
        candidates = data.get("candidates", [])
        if candidates:
            text = candidates[0].get("content", {}).get("parts", [{}])[0].get("text", "")
            class MockResponse:
                def __init__(self, content):
                    self.content = content
            return MockResponse(text)
        raise RuntimeError(f"Gemini returned no candidates: {data}")


@dataclass
class LLM:
    _impl: Any           # a LangChain chat model or GeminiLLM
    name: str            # human-readable, e.g. "hf:Qwen/Qwen2.5-7B-Instruct"

    def generate(self, system: str, user: str) -> str:
        from langchain_core.messages import SystemMessage, HumanMessage
        out = self._impl.invoke([SystemMessage(content=system), HumanMessage(content=user)])
        return out.content if hasattr(out, "content") else str(out)


def make_llm() -> LLM:
    backend = os.getenv("LLM_BACKEND", "ollama").lower()
    temperature = max(float(os.getenv("LLM_TEMPERATURE", "0.4")), 0.01)  # HF rejects exactly 0
    max_tokens = int(os.getenv("LLM_MAX_TOKENS", "2048"))

    if backend == "hf":
        from langchain_huggingface import ChatHuggingFace, HuggingFaceEndpoint
        token = os.environ.get("HUGGINGFACEHUB_API_TOKEN")
        if not token:
            raise RuntimeError("LLM_BACKEND=hf but HUGGINGFACEHUB_API_TOKEN is not set")
        model = os.getenv("HF_MODEL", "Qwen/Qwen2.5-72B-Instruct")
        # task="conversational" -> HF Inference Providers chat-completions API
        # (instruct/chat models are no longer served as plain text-generation).
        endpoint = HuggingFaceEndpoint(
            repo_id=model,
            task="conversational",
            huggingfacehub_api_token=token,
            temperature=temperature,
            max_new_tokens=max_tokens,
        )
        return LLM(_impl=ChatHuggingFace(llm=endpoint), name=f"hf:{model}")

    if backend == "ollama":
        from langchain_ollama import ChatOllama
        model = os.getenv("OLLAMA_MODEL", "llama3.1")
        impl = ChatOllama(model=model, temperature=temperature, num_predict=max_tokens)
        return LLM(_impl=impl, name=f"ollama:{model}")

    if backend == "gemini":
        token = os.environ.get("GEMINI_API_KEY")
        if not token:
            raise RuntimeError("LLM_BACKEND=gemini but GEMINI_API_KEY is not set")
        model = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
        impl = GeminiLLM(api_key=token, model=model, temperature=temperature, max_tokens=max_tokens)
        return LLM(_impl=impl, name=f"gemini:{model}")

    raise ValueError(f"Unknown LLM_BACKEND={backend!r}. Use 'hf', 'gemini', or 'ollama'.")
