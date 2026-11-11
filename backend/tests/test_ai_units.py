from types import SimpleNamespace

import pytest

from app.adapters.ai.anthropic_provider import FALLBACK_BETA, AnthropicProvider
from app.adapters.ai.base import (
    AgentOutput,
    AgentRequest,
    AIProviderError,
    ChatTurn,
    KnowledgeContext,
)
from app.adapters.ai.openai_provider import OpenAIProvider
from app.adapters.ai.prompts import build_messages, build_system_prompt
from app.adapters.ai.text_match import best_match, find_mentions
from app.core.config import ConfigurationError
from app.services.qualification_service import (
    DecisionInput,
    decide,
    empty_fields,
    ungrounded_amounts,
    validate_domicile,
    validate_name,
    validate_vehicle,
)
from app.services.settings_service import render_template
from tests.conftest import make_settings

CATALOG = {"Xpander": ["expander"], "Xpander Cross": [], "Pajero Sport": ["pajero"]}


# ------------------------------------------------------------ validators
@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("andi", "Andi"),
        ("Pak Budi Santoso", "Budi Santoso"),
        ("ok", None),
        ("123", None),
        ("a b c d e", None),
        ("", None),
    ],
)
def test_validate_name(raw, expected):
    assert validate_name(raw) == expected


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("medan", "Medan"),
        ("di Bekasi", "Bekasi"),
        ("bks", "Bekasi"),
        ("Kabupaten Bogor", "Kabupaten Bogor"),
        ("rumah", None),
        ("12345", None),
    ],
)
def test_validate_domicile(raw, expected):
    assert validate_domicile(raw, {"Bekasi": ["bks"]}) == expected


def test_validate_vehicle_uses_catalog_and_typos():
    assert validate_vehicle("expander", CATALOG) == "Xpander"
    assert validate_vehicle("Pajero Sprot", CATALOG) == "Pajero Sport"
    assert validate_vehicle("xpander cross", CATALOG) == "Xpander Cross"
    assert validate_vehicle("Avanza", CATALOG) is None
    assert validate_vehicle("Avanza", {}) == "Avanza"  # no catalog configured -> raw accepted


def test_find_mentions_prefers_longer_alias():
    assert find_mentions("mau xpander cross dong", CATALOG) == [(1, "Xpander Cross")]
    assert best_match("mitsubishi pajero", CATALOG) == "Pajero Sport"


# ------------------------------------------------------------ grounding guard
def test_ungrounded_amounts():
    kb = KnowledgeContext(text="- harga Xpander: Rp 300.000.000 (OTR)\n- DP mulai 20%")
    assert ungrounded_amounts("Harganya Rp 300.000.000", kb) == set()
    assert ungrounded_amounts("Harganya 300 juta", kb) == set()
    assert ungrounded_amounts("DP 20% saja", kb) == set()
    assert ungrounded_amounts("Diskon 15 juta dan DP 10%", kb) == {15_000_000, 10}
    assert ungrounded_amounts("Halo, siapa nama Anda?", kb) == set()


# ------------------------------------------------------------ decision engine
def _inp(fields, output, **kw):
    return DecisionInput(
        fields=fields,
        output=output,
        knowledge=KnowledgeContext(vehicle_catalog=CATALOG),
        city_catalog={},
        max_asks=kw.get("max_asks", 2),
        is_first_reply=kw.get("first", False),
        consecutive_ai_failures=kw.get("failures", 0),
        messages={"closing": "CLOSING", "human": "HUMAN", "ai_unavailable": "DOWN"},
    )


def _out(**kw):
    base = dict(
        customer_name="",
        domicile="",
        vehicle_model="",
        declined_fields=[],
        intent="other",
        asked_field="name",
        reply="Boleh tahu nama?",
    )
    return AgentOutput(**(base | kw))


def test_decide_never_erases_known_values():
    fields = empty_fields()
    fields["name"].update(status="collected", value="Andi")
    d = decide(_inp(fields, _out(asked_field="domicile", reply="Domisili di mana?")))
    assert d.fields["name"]["value"] == "Andi"
    assert d.asked_field == "domicile" and d.reply_source == "ai"


def test_decide_wrong_field_from_ai_uses_template():
    d = decide(_inp(empty_fields(), _out(asked_field="vehicle", reply="Mau unit apa?")))
    assert d.reply_source == "template" and d.asked_field == "name"


def test_decide_counts_asks_and_skips_after_max():
    fields = empty_fields()
    fields["name"]["asks"] = 2
    d = decide(_inp(fields, _out(asked_field="domicile", reply="Domisili?")))
    assert d.fields["name"]["status"] == "declined"
    assert d.fields["domicile"]["asks"] == 1


def test_decide_completion_is_backend_rule():
    d = decide(
        _inp(
            empty_fields(),
            _out(
                customer_name="Andi", domicile="Medan", vehicle_model="expander", asked_field="none"
            ),
        )
    )
    assert d.handover_reason == "qualification_complete" and d.reply == "CLOSING"
    assert d.fields["vehicle"]["value"] == "Xpander"


def test_render_template_is_safe():
    # Missing values and unknown placeholders become empty instead of crashing.
    result = render_template("Halo {nama}, unit {unit}. {lain}", {"nama": "Andi", "unit": None})
    assert result == "Halo Andi, unit ."


# ------------------------------------------------------------ prompts
def _request():
    return AgentRequest(
        history=[
            ChatTurn("assistant", "lama"),
            ChatTurn("contact", "Halo"),
            ChatTurn("contact", "saya Andi"),
            ChatTurn("assistant", "Domisili?"),
        ],
        known={"name": "Andi", "domicile": None, "vehicle": None},
        field_status={"name": "collected", "domicile": "missing", "vehicle": "missing"},
        missing_fields=["domicile", "vehicle"],
        last_asked_field="domicile",
        is_first_reply=False,
        knowledge=KnowledgeContext(vehicle_models=["Xpander"], text="## FAQ\n- Jam: 08-17"),
    )


def test_build_messages_starts_with_user_and_merges_turns():
    assert build_messages(_request().history) == [
        {"role": "user", "content": "Halo\nsaya Andi"},
        {"role": "assistant", "content": "Domisili?"},
    ]


def test_system_prompt_contains_rules_state_and_knowledge():
    prompt = build_system_prompt(_request())
    assert "DILARANG mengarang harga" in prompt
    assert "nama customer: Andi [collected]" in prompt
    assert "## FAQ" in prompt and "Xpander" in prompt


# ------------------------------------------------------------ providers (fake SDK clients)
def _agent_output():
    return AgentOutput(
        customer_name="Andi",
        domicile="",
        vehicle_model="",
        declined_fields=[],
        intent="provide_info",
        asked_field="domicile",
        reply="Domisili di mana?",
    )


class FakeAnthropic:
    def __init__(self, response):
        self.calls = []
        self.beta = SimpleNamespace(messages=SimpleNamespace(parse=self._parse))
        self._response = response

    async def _parse(self, **kwargs):
        self.calls.append(kwargs)
        return self._response


async def test_anthropic_provider_request_and_response():
    response = SimpleNamespace(
        stop_reason="end_turn",
        parsed_output=_agent_output(),
        model="claude-opus-5-5",
        usage=SimpleNamespace(input_tokens=120, output_tokens=40),
    )
    fake = FakeAnthropic(response)
    settings = make_settings(ai_provider="anthropic", anthropic_api_key="dummy-key")
    provider = AnthropicProvider(settings, client=fake)
    result = await provider.run_turn(_request())
    assert result.output.customer_name == "Andi" and result.input_tokens == 120
    call = fake.calls[0]
    assert call["model"] == "claude-opus-5-5"
    assert call["output_format"] is AgentOutput
    assert call["output_config"] == {"effort": "medium"}
    assert call["betas"] == [FALLBACK_BETA] and call["fallbacks"] == "default"
    assert call["messages"][0]["role"] == "user"


async def test_anthropic_refusal_raises():
    response = SimpleNamespace(
        stop_reason="refusal",
        parsed_output=None,
        model="m",
        usage=SimpleNamespace(input_tokens=1, output_tokens=0),
    )
    provider = AnthropicProvider(
        make_settings(ai_provider="anthropic", anthropic_api_key="k"),
        client=FakeAnthropic(response),
    )
    with pytest.raises(AIProviderError) as exc:
        await provider.run_turn(_request())
    assert exc.value.status == "refusal"


async def test_openai_provider_request_and_response():
    calls = []

    async def parse(**kwargs):
        calls.append(kwargs)
        message = SimpleNamespace(parsed=_agent_output(), refusal=None)
        return SimpleNamespace(
            choices=[SimpleNamespace(message=message, finish_reason="stop")],
            model="dummy-model",
            usage=SimpleNamespace(prompt_tokens=10, completion_tokens=5),
        )

    fake = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(parse=parse)))
    settings = make_settings(ai_provider="openai", openai_api_key="dummy", ai_model="dummy-model")
    result = await OpenAIProvider(settings, client=fake).run_turn(_request())
    assert result.output.asked_field == "domicile"
    assert calls[0]["messages"][0]["role"] == "system"
    assert calls[0]["response_format"] is AgentOutput


def test_ai_provider_config_requires_api_keys():
    with pytest.raises(ConfigurationError, match="ANTHROPIC_API_KEY"):
        make_settings(ai_provider="anthropic")
    with pytest.raises(ConfigurationError, match="AI_MODEL"):
        make_settings(ai_provider="openai", openai_api_key="k")
    assert (
        make_settings(ai_provider="anthropic", anthropic_api_key="k").resolved_ai_model
        == "claude-opus-5-5"
    )
