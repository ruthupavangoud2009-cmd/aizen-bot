"""
Kyoka 3.0 - Core Engine
"""

"""
Kyoka 3.0 - Core Engine
"""

def __getattr__(name: str):
    if name == "KyokaBot":
        from src.core.bot import KyokaBot
        return KyokaBot
    if name == "Config":
        from src.core.config import Config
        return Config
    if name in ("TaskManager", "SpamTaskInfo", "SpamControlView"):
        import src.core.task_manager as tm
        return getattr(tm, name)
    if name in ("FeatureRegistry", "FeatureInfo"):
        import src.core.feature_registry as fr
        return getattr(fr, name)
    if name in ("CommandRegistry", "CommandMetadata"):
        import src.core.command_registry as cr
        return getattr(cr, name)
    if name in ("is_bot_owner", "is_server_admin", "check_hierarchy", "can_moderate", "require_owner", "require_guild_permissions"):
        import src.core.permissions as p
        return getattr(p, name)
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
