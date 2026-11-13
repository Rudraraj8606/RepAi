# test_llm_text.py -- checks that model replies always come out as plain text.

from agents.llm_text import message_text


def test_a_plain_string_is_returned_unchanged():
    assert message_text("Next session: 205 lbs x 10") == "Next session: 205 lbs x 10"


def test_thinking_blocks_are_dropped_and_only_the_text_is_kept():
    # The shape Claude returned when the plan printed as a list of dicts.
    content = [
        {"type": "thinking", "thinking": "", "signature": "abc123"},
        {"type": "text", "text": "Next Session Plan: Hack Squats"},
    ]

    assert message_text(content) == "Next Session Plan: Hack Squats"


def test_several_text_blocks_are_joined_in_order():
    content = [
        {"type": "text", "text": "Part one. "},
        {"type": "text", "text": "Part two."},
    ]

    assert message_text(content) == "Part one. Part two."


def test_plain_strings_inside_a_list_are_kept():
    assert message_text(["Hello ", "there"]) == "Hello there"