from enum import Enum, IntFlag
from typing import List


class ResourceAction(IntFlag):
    """Generic bitwise resource permissions.

    These flags are provider-agnostic. They happen to match HexIAM's
    bitmask layout, but any IAM implementation may use them by mapping
    its own action vocabulary to/from this enum.
    """
    READ     = 1 << 0   # view/query/get
    WRITE    = 1 << 1   # create/update/modify
    DELETE   = 1 << 2   # remove/purge
    APPROVE  = 1 << 3   # approve/authorize/accept
    REJECT   = 1 << 4   # reject/deny/disallow
    EXECUTE  = 1 << 5   # run/deploy/trigger
    ASSIGN   = 1 << 6   # grant/revoke/attach
    MANAGE   = 1 << 7   # admin-level (settings, ownership)
    EXPORT   = 1 << 8   # download/report/export data
    IMPORT   = 1 << 9   # upload/import data
    ACTIVATE = 1 << 10  # enable/disable/suspend
    ARCHIVE  = 1 << 11  # archive/restore


# Backwards-compatible alias for historical references.
HEXIAMAction = ResourceAction


# Lowercase action-name -> bit mapping (mirrors HEXIAM's vocabulary).
resource_action_map = {
    'read': ResourceAction.READ,
    'write': ResourceAction.WRITE,
    'delete': ResourceAction.DELETE,
    'approve': ResourceAction.APPROVE,
    'reject': ResourceAction.REJECT,
    'execute': ResourceAction.EXECUTE,
    'assign': ResourceAction.ASSIGN,
    'manage': ResourceAction.MANAGE,
    'export': ResourceAction.EXPORT,
    'import': ResourceAction.IMPORT,
    'activate': ResourceAction.ACTIVATE,
    'archive': ResourceAction.ARCHIVE,
}
# Backwards-compatible alias.
hex_iam_permission_map = resource_action_map


def bitmask_to_action_names(mask: int) -> List[str]:
    """Convert a bitmask into the list of action name strings."""
    return [name for name, flag in resource_action_map.items() if mask & int(flag)]


class GenericResources(str, Enum):
    """Stable resource identifiers HexShare uses against the IAM provider.

    Group/room resources are not enumerated here; they use the
    ``DOCUMENT_GROUP_PREFIX`` namespace with opaque per-group IDs.
    """
    DOCUMENTS = "documents"


# Prefix used for all per-room/group resource IDs registered with the IAM.
# Example: ``dcgrp_01JTK9E6M9W7A3...``
DOCUMENT_GROUP_PREFIX = "dcgrp_"


OIDC_TMP_COOKIE = "hexshare_oidc_tmp"
AUTH_COOKIE = "hexshare_access_token"
REFRESH_COOKIE = "hexshare_refresh_token"