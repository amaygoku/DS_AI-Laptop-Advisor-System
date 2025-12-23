import pytest
from llm.parse import parse_llm_json_strict

def test_single_intent_ok():
    q = parse_llm_json_strict('{"user_type":"gaming","price_max":30000000}')
    assert q["user_type"] == "gaming"
    assert q["price_max"] == 30000000
    assert "user_types" not in q

def test_multi_intent_ok():
    q = parse_llm_json_strict('{"user_types":["study","gaming"],"price_max":20000000}')
    assert q["user_types"] == ["study", "gaming"]
    assert "user_type" not in q

def test_user_types_len_1_rejected():
    with pytest.raises(ValueError):
        parse_llm_json_strict('{"user_types":["gaming"]}')

def test_both_user_type_and_user_types_rejected():
    with pytest.raises(ValueError):
        parse_llm_json_strict('{"user_type":"study","user_types":["study","gaming"]}')

def test_drop_unknown_keys():
    q = parse_llm_json_strict('{"user_type":"study","brand":"Dell","price_max":20000000}')
    assert "brand" not in q
    assert q["user_type"] == "study"
