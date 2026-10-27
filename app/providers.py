"""Pluggable model providers.

Every provider exposes two methods: embed(texts) and chat(system, user).
Swap providers with one env var: LLM_PROVIDER=fake|openai|ollama.
"""
from __future__ import annotations

import hashlib
import math
import re
from dataclasses import dataclass

import httpx

from .config import Settings

DIM = 1024  # fake provider dimension (bigger = fewer hash collisions)


@dataclass
class ChatResult:
    text: str
    tokens_in: int
    tokens_out: int


def rough_tokens(text: str) -> int:
    """About 4 characters per token. Good enough for cost estimates."""
    return max(1, len(text) // 4)


_WORD = re.compile(r"[a-z0-9]+")
_STOP = set("the a an of to and or in on for is are be by with what who how when does do i my at as it this that which from must".split())


def words(text: str) -> list[str]:
    return [w for w in _WORD.findall(text.lower()) if w not in _STOP]


class FakeProvider:
    """Offline provider. Hashed bag-of-words embeddings and an extractive 'answer'.

    It is not smart. It exists so tests, CI and demos run with no key and no GPU,
    and so retrieval and access control can be tested deterministically.
    """

    name = "fake"

    def embed(self, texts: list[str]) -> list[list[float]]:
        out = []
        for t in texts:
            v = [0.0] * DIM
            for w in words(t):
                h = int(hashlib.md5(w.encode()).hexdigest(), 16)
                v[h % DIM] += 1.0
            n = math.sqrt(sum(x * x for x in v)) or 1.0
            out.append([x / n for x in v])
        return out

    def chat(self, system: str, user: str) -> ChatResult:
        # Return the context sentence that shares the most words with the question.
        q, _, ctx = user.partition("\n\nContext:\n")
        qw = set(words(q))
        sents = [s.strip() for line in ctx.splitlines() for s in re.split(r"(?<=[.!?])\s+", line)]
        sents = [s for s in sents if len(s) > 20]
        # Weight each question word by how rare it is in the context (a tiny IDF),
        # so "Bastrop" counts more than "Mansfield" when every sentence says Mansfield.
        df = {w: sum(w in set(words(s)) for s in sents) for w in qw}
        best, score = "I don't know based on the documents I can access.", 0.0
        for sent in sents:
            sw = set(words(sent))
            sc = sum(1.0 / df[w] for w in qw & sw if df[w])
            if sc > score:
                best, score = sent, sc
        cite = re.search(r"\[(\d+)\]", ctx)
        text = best + (f" [{cite.group(1)}]" if score and cite else "")
        return ChatResult(text, rough_tokens(system + user), rough_tokens(text))


class OpenAIProvider:
    """Any OpenAI-compatible API (OpenAI, Azure OpenAI, vLLM, LM Studio, ...)."""

    name = "openai"

    def __init__(self, s: Settings):
        if not s.openai_key:
            raise RuntimeError("OPENAI_API_KEY is not set. Use LLM_PROVIDER=fake for offline mode.")
        self.s = s
        self.http = httpx.Client(base_url=s.openai_base, timeout=60,
                                 headers={"Authorization": f"Bearer {s.openai_key}"})

    def embed(self, texts):
        r = self.http.post("/embeddings", json={"model": self.s.openai_embed, "input": texts})
        r.raise_for_status()
        return [d["embedding"] for d in r.json()["data"]]

    def chat(self, system, user):
        r = self.http.post("/chat/completions", json={
            "model": self.s.openai_chat, "temperature": 0,
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}]})
        r.raise_for_status()
        j = r.json()
        u = j.get("usage", {})
        text = j["choices"][0]["message"]["content"]
        return ChatResult(text, u.get("prompt_tokens", rough_tokens(user)),
                          u.get("completion_tokens", rough_tokens(text)))


class OllamaProvider:
    """Fully on-prem. No data leaves the building."""

    name = "ollama"

    def __init__(self, s: Settings):
        self.s = s
        self.http = httpx.Client(base_url=s.ollama_base, timeout=120)

    def embed(self, texts):
        r = self.http.post("/api/embed", json={"model": self.s.ollama_embed, "input": texts})
        r.raise_for_status()
        return r.json()["embeddings"]

    def chat(self, system, user):
        r = self.http.post("/api/chat", json={
            "model": self.s.ollama_chat, "stream": False, "options": {"temperature": 0},
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}]})
        r.raise_for_status()
        j = r.json()
        text = j["message"]["content"]
        return ChatResult(text, j.get("prompt_eval_count", rough_tokens(user)),
                          j.get("eval_count", rough_tokens(text)))


def get_provider(s: Settings):
    return {"fake": lambda: FakeProvider(), "openai": lambda: OpenAIProvider(s),
            "ollama": lambda: OllamaProvider(s)}[s.provider]()
