"""
Kyoka 3.0 - Core Engine
"""

from src.core.config import Config
from src.core.task_manager import TaskManager, SpamTaskInfo, SpamControlView
from src.core.feature_registry import FeatureRegistry, FeatureInfo
from src.core.command_registry import CommandRegistry, CommandMetadata
from src.core.permissions import is_bot_owner, is_server_admin, check_hierarchy, can_moderate, require_owner, require_guild_permissions

def __getattr__(name: str):
    if name == "KyokaBot":
        from src.core.bot import KyokaBot
        return KyokaBot
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

__all__ = [
    "KyokaBot",
    "Config",
    "TaskManager",
    "SpamTaskInfo",
    "SpamControlView",
    "FeatureRegistry",
    "FeatureInfo",
    "CommandRegistry",
    "CommandMetadata",
    "is_bot_owner",
    "is_server_admin",
    "check_hierarchy",
    "can_moderate",
    "require_owner",
    "require_guild_permissions",
]
