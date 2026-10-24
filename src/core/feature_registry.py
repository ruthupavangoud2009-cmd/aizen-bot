"""
Kyoka 3.0 - Feature Registry
Central registry tracking all installed features, extensions, command bindings,
permissions, dependencies, and health/load status.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Set

if TYPE_CHECKING:
    from src.core.bot import KyokaBot

logger = logging.getLogger("Kyoka.Core.FeatureRegistry")


@dataclass
class FeatureInfo:
    """Metadata tracking an installed feature module in Kyoka."""
    name: str
    extension_path: str
    category: str
    description: str = ""
    enabled: bool = True
    health_status: str = "healthy"  # "healthy", "failed", "degraded", "disabled"
    error_message: Optional[str] = None
    commands: List[str] = field(default_factory=list)
    slash_commands: List[str] = field(default_factory=list)
    required_permissions: List[str] = field(default_factory=list)
    dependencies: List[str] = field(default_factory=list)
    config_requirements: List[str] = field(default_factory=list)


class FeatureRegistry:
    """Manages feature discovery, lifecycle state, health validation, and permissions."""

    def __init__(self, bot: Optional[KyokaBot] = None) -> None:
        self.bot = bot
        self._features: Dict[str, FeatureInfo] = {}

    def register_feature(
        self,
        name: str,
        extension_path: str,
        category: str,
        description: str = "",
        dependencies: Optional[List[str]] = None,
        required_permissions: Optional[List[str]] = None,
        config_requirements: Optional[List[str]] = None,
    ) -> FeatureInfo:
        """Register a feature specification."""
        feature = FeatureInfo(
            name=name,
            extension_path=extension_path,
            category=category,
            description=description,
            dependencies=dependencies or [],
            required_permissions=required_permissions or [],
            config_requirements=config_requirements or [],
        )
        self._features[name.lower()] = feature
        return feature

    def get_feature(self, name: str) -> Optional[FeatureInfo]:
        """Fetch a feature by name (case-insensitive)."""
        return self._features.get(name.lower())

    def get_all_features(self) -> Dict[str, FeatureInfo]:
        """Return all registered features."""
        return dict(self._features)

    def get_features_by_category(self, category: str) -> List[FeatureInfo]:
        """Return all features within a specific help or functional category."""
        target = category.lower()
        return [f for f in self._features.values() if f.category.lower() == target]

    def update_health(self, name: str, status: str, error: Optional[str] = None) -> None:
        """Update runtime health status of a feature."""
        feat = self.get_feature(name)
        if feat:
            feat.health_status = status
            feat.error_message = error
            logger.info(f"[FeatureRegistry] Feature '{feat.name}' health updated: {status} (err: {error})")

    def is_enabled(self, name: str) -> bool:
        """Check if feature is currently enabled and healthy."""
        feat = self.get_feature(name)
        return feat.enabled and feat.health_status == "healthy" if feat else False

    def enable_feature(self, name: str) -> bool:
        """Mark a feature as enabled."""
        feat = self.get_feature(name)
        if feat:
            feat.enabled = True
            return True
        return False

    def disable_feature(self, name: str) -> bool:
        """Mark a feature as disabled."""
        feat = self.get_feature(name)
        if feat:
            feat.enabled = False
            feat.health_status = "disabled"
            return True
        return False

    def audit_system_features(self, bot: Any) -> Dict[str, Any]:
        """
        Inspect live bot instance and sync feature states:
        - Check loaded extensions against bot.extensions
        - Check failed extensions in bot.failed_extensions
        - Enumerate commands per cog
        """
        loaded_exts = set(getattr(bot, "extensions", {}).keys())
        failed_exts = getattr(bot, "failed_extensions", {})

        for name, feat in self._features.items():
            if feat.extension_path in failed_exts:
                feat.health_status = "failed"
                feat.error_message = failed_exts[feat.extension_path]
            elif feat.extension_path in loaded_exts:
                feat.health_status = "healthy"
                feat.error_message = None
            else:
                feat.health_status = "unloaded"

        # Populate commands per feature from registered cogs
        cogs = getattr(bot, "cogs", {})
        for cog_name, cog_inst in cogs.items():
            feat = self.get_feature(cog_name)
            if feat:
                feat.commands = [cmd.name for cmd in cog_inst.get_commands()]
                feat.slash_commands = [cmd.name for cmd in getattr(cog_inst, "get_app_commands", lambda: [])()]

        return {
            "total_features": len(self._features),
            "healthy": sum(1 for f in self._features.values() if f.health_status == "healthy"),
            "failed": sum(1 for f in self._features.values() if f.health_status == "failed"),
            "unloaded": sum(1 for f in self._features.values() if f.health_status == "unloaded"),
        }
