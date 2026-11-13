"""
llm_text.py  --  turn a LangChain message's content into plain text.

Newer Claude models can reply with a LIST of content blocks (for example a
"thinking" block followed by the "text" block) instead of a plain string.
The agent functions are supposed to return a str, so they run what the model
gave them through message_text() first.
"""


def message_text(content) -> str:
    """Return only the text from a message's content, whether it's a str or a list of blocks."""
    if isinstance(content, str):
        return content

    parts = []
    for block in content:
        if isinstance(block, str):
            parts.append(block)
        elif isinstance(block, dict) and block.get("type") == "text":
            parts.append(block.get("text", ""))
    return "".join(parts)