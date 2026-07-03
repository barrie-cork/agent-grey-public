"""
TypedDict definitions for Core app models.
Created during Phase 2 of TypedDict migration - Model Alignment.
Part of VSA-compliant model type system.
"""

from typing import Any, Dict, List, Optional, TypedDict, Union

# JSONField Type for Configuration.value
ConfigValueType = Union[str, int, float, bool, None, List[Any], Dict[str, Any]]


class ConfigurationData(TypedDict):
    """Serialized representation of Configuration model.

    Used for configuration management API responses.
    """

    id: str  # UUID as string
    key: str
    value: ConfigValueType  # JSON-serializable value
    description: str
    created_at: str  # ISO format timestamp
    updated_at: str  # ISO format timestamp
    updated_by_id: Optional[str]  # UUID as string
    updated_by_username: Optional[str]  # Denormalized for display


class ConfigurationSummary(TypedDict):
    """Lightweight configuration for lists."""

    key: str
    value: ConfigValueType
    description: str


class ConfigurationBulkUpdate(TypedDict):
    """Structure for bulk configuration updates."""

    configs: Dict[str, ConfigValueType]  # key: value pairs
    user_id: Optional[str]  # UUID as string


class ConfigurationChangeLog(TypedDict):
    """Configuration change tracking."""

    key: str
    old_value: ConfigValueType
    new_value: ConfigValueType
    changed_at: str  # ISO format timestamp
    changed_by: Optional[str]  # Username
