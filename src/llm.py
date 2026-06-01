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
from dataclasses import dataclass
from typing import Any


@dataclass
class LLM:
    _impl: Any           # a LangChain chat model (ChatHuggingFace or ChatOllama)
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
        model = os.getenv("HF_MODEL", "Qwen/Qwen2.5-7B-Instruct")
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

    raise ValueError(f"Unknown LLM_BACKEND={backend!r}. Use 'hf' or 'ollama'.")
