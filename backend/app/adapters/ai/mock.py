"""Deterministic AI for development & tests (no internet, no cost).

Phase 1 only needs "an AI reply arrives". Real lead qualification (asking for
name, domicile, unit and extracting them) is built in a later phase.
"""

from app.adapters.ai.base import AIReply, ChatTurn

GREETING = (
    "Halo, terima kasih sudah menghubungi Mitsubishi DIPO! "
    "Boleh kami tahu nama Bapak/Ibu? (balasan AI simulasi)"
)


class MockAIProvider:
    name = "mock"

    async def generate_reply(self, history: list[ChatTurn]) -> AIReply:
        assistant_turns = [t for t in history if t.role == "assistant"]
        last_contact = next((t.text for t in reversed(history) if t.role == "contact"), "")
        if not assistant_turns:
            return AIReply(text=GREETING, provider=self.name)
        return AIReply(
            text=f'Terima kasih, pesan Anda "{last_contact}" sudah kami terima. '
            "(balasan AI simulasi)",
            provider=self.name,
        )
