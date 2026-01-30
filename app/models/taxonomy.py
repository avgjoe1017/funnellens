"""Content type taxonomy for creator posts."""

from enum import Enum


class ContentType(str, Enum):
    """Content categories for social media posts."""

    STORYTIME = "storytime"
    GRWM = "grwm"
    THIRST_TRAP = "thirst_trap"
    BEHIND_SCENES = "behind_scenes"
    MONEY_TALK = "money_talk"
    OTHER = "other"


DEFAULT_TAXONOMY = {
    "storytime": {
        "label": "Storytime",
        "description": "Work stories, client stories, life narratives",
        "keywords": ["story", "happened", "client", "work", "crazy", "told", "said", "omg"],
        "hotkey": "1",
    },
    "grwm": {
        "label": "GRWM / Talk to Camera",
        "description": "Get ready with me, direct address, conversational",
        "keywords": ["grwm", "get ready", "chat", "talk", "honest", "real talk", "rant"],
        "hotkey": "2",
    },
    "thirst_trap": {
        "label": "Thirst Trap",
        "description": "Aesthetic-focused, minimal narrative, visual appeal",
        "keywords": ["outfit", "fit check", "look", "vibe"],
        "hotkey": "3",
    },
    "behind_scenes": {
        "label": "Behind the Scenes",
        "description": "Day in life, club vlogs, BTS content",
        "keywords": ["vlog", "day in", "bts", "behind", "come with", "pov", "routine"],
        "hotkey": "4",
    },
    "money_talk": {
        "label": "Money / Income",
        "description": "Earnings breakdowns, income proof, money motivation",
        "keywords": ["made", "earned", "income", "money", "$$", "k this", "profit", "bag"],
        "hotkey": "5",
    },
    "other": {
        "label": "Other",
        "description": "Doesn't fit other categories",
        "keywords": [],
        "hotkey": "6",
    },
}
