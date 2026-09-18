from radio.plugins.qq_music_bot import _send_private_to_all_bots
from radio.plugins.qq_music_bot.channels import (
    C2C_PREFIX,
    DMS_PREFIX,
    ONEBOT_PREFIX,
    encode_uid,
    split_uid,
)


class FakeBot:
    def __init__(self, type_: str):
        self.type = type_
        self.calls: list = []

    async def call_api(self, api, **kwargs):
        self.calls.append(("call_api", api, kwargs))

    async def send_to_c2c(self, **kwargs):
        self.calls.append(("send_to_c2c", kwargs))

    async def send_to_dms(self, **kwargs):
        self.calls.append(("send_to_dms", kwargs))


def test_encode_and_split_uid():
    assert encode_uid(ONEBOT_PREFIX, "123") == "onebot:123"
    assert encode_uid(C2C_PREFIX, "AbC") == "c2c:AbC"
    assert encode_uid(DMS_PREFIX, "g1", "u2") == "dms:g1:u2"
    assert split_uid("onebot:123") == ("onebot", ["123"])
    assert split_uid("c2c:AbC") == ("c2c", ["AbC"])
    assert split_uid("dms:g1:u2") == ("dms", ["g1", "u2"])
    assert split_uid("legacy-id") == ("", ["legacy-id"])


async def test_send_onebot_only_strips_prefix():
    onebot = FakeBot("OneBot V11")
    qq = FakeBot("QQ")
    ok = await _send_private_to_all_bots({"a": onebot, "b": qq}, "onebot:123", "hi")
    assert ok
    assert onebot.calls == [("call_api", "send_private_msg", {"user_id": "123", "message": "hi"})]
    assert qq.calls == []


async def test_send_c2c_uses_openid():
    onebot = FakeBot("OneBot V11")
    qq = FakeBot("QQ")
    ok = await _send_private_to_all_bots({"a": onebot, "b": qq}, "c2c:OpenId", "hi")
    assert ok
    assert onebot.calls == []
    assert len(qq.calls) == 1
    method, kwargs = qq.calls[0]
    assert method == "send_to_c2c"
    assert kwargs["openid"] == "OpenId"


async def test_send_dms_uses_guild_id():
    qq = FakeBot("QQ")
    ok = await _send_private_to_all_bots({"b": qq}, "dms:987654:321", "hi")
    assert ok
    method, kwargs = qq.calls[0]
    assert method == "send_to_dms"
    assert kwargs["guild_id"] == "987654"


async def test_send_unknown_prefix_returns_false():
    onebot = FakeBot("OneBot V11")
    qq = FakeBot("QQ")
    assert not await _send_private_to_all_bots({"a": onebot, "b": qq}, "1692038362", "hi")
    assert not await _send_private_to_all_bots({"a": onebot, "b": qq}, "wechat:1", "hi")
    assert onebot.calls == []
    assert qq.calls == []


async def test_send_retries_next_same_type_bot():
    class FailingBot(FakeBot):
        async def send_to_c2c(self, **kwargs):
            raise RuntimeError("boom")

    failing = FailingBot("QQ")
    healthy = FakeBot("QQ")
    ok = await _send_private_to_all_bots({"a": failing, "b": healthy}, "c2c:OpenId", "hi")
    assert ok
    assert healthy.calls[0][1]["openid"] == "OpenId"
