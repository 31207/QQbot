from radio.plugins.qq_music_bot.channels import (
    C2C_PREFIX,
    DMS_PREFIX,
    ONEBOT_PREFIX,
    encode_uid,
    split_uid,
)


def test_encode_and_split_uid():
    assert encode_uid(ONEBOT_PREFIX, "123") == "onebot:123"
    assert encode_uid(C2C_PREFIX, "AbC") == "c2c:AbC"
    assert encode_uid(DMS_PREFIX, "g1", "u2") == "dms:g1:u2"
    assert split_uid("onebot:123") == ("onebot", ["123"])
    assert split_uid("c2c:AbC") == ("c2c", ["AbC"])
    assert split_uid("dms:g1:u2") == ("dms", ["g1", "u2"])
    assert split_uid("legacy-id") == ("", ["legacy-id"])
