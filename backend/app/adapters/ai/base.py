from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class ChatTurn:
    role: str  # "contact" | "assistant"
    text: str


@dataclass(frozen=True)
class AIReply:
    text: str
    provider: str


class AIProvider(Protocol):
    name: str

    async def generate_reply(self, history: list[ChatTurn]) -> AIReply: ...
