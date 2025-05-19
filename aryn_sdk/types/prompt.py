from enum import Enum


class PromptType(str, Enum):
    # System prompt for the frontend chat tool.
    CHAT_SYSTEM = "CHAT_SYSTEM"
