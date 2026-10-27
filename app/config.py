"""All settings come from environment variables so the same image runs hosted or on-prem."""
import os
from dataclasses import dataclass, field


def _env(name: str, default: str = "") -> str:
    return os.environ.get(name, default)


@dataclass
class Settings:
    provider: str = field(default_factory=lambda: _env("LLM_PROVIDER", "fake"))
    openai_key: str = field(default_factory=lambda: _env("OPENAI_API_KEY"))
    openai_base: str = field(default_factory=lambda: _env("OPENAI_BASE_URL", "https://api.openai.com/v1"))
    openai_chat: str = field(default_factory=lambda: _env("OPENAI_CHAT_MODEL", "gpt-4o-mini"))
    openai_embed: str = field(default_factory=lambda: _env("OPENAI_EMBED_MODEL", "text-embedding-3-small"))
    ollama_base: str = field(default_factory=lambda: _env("OLLAMA_BASE_URL", "http://localhost:11434"))
    ollama_chat: str = field(default_factory=lambda: _env("OLLAMA_CHAT_MODEL", "llama3.1:8b"))
    ollama_embed: str = field(default_factory=lambda: _env("OLLAMA_EMBED_MODEL", "nomic-embed-text"))
    database_url: str = field(default_factory=lambda: _env("DATABASE_URL"))
    sqlite_path: str = field(default_factory=lambda: _env("SQLITE_PATH", "rag.db"))
    price_in: float = field(default_factory=lambda: float(_env("PRICE_INPUT_PER_M", "0.15")))
    price_out: float = field(default_factory=lambda: float(_env("PRICE_OUTPUT_PER_M", "0.60")))
    top_k: int = field(default_factory=lambda: int(_env("TOP_K", "4")))
