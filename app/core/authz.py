from enum import IntFlag

# Based on HEXIAM permissions
class HEXIAMAction(IntFlag):
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

# Based on HEXIAM permissions
hex_iam_permission_map = {
    'read': HEXIAMAction.READ,
    'write': HEXIAMAction.WRITE,
    'delete': HEXIAMAction.DELETE,
    'approve': HEXIAMAction.APPROVE,
    'reject': HEXIAMAction.REJECT,
    'execute': HEXIAMAction.EXECUTE,
    'assign': HEXIAMAction.ASSIGN,
    'manage': HEXIAMAction.MANAGE,
    'export': HEXIAMAction.EXPORT,
    'import': HEXIAMAction.IMPORT,
    'activate': HEXIAMAction.ACTIVATE,
    'archive': HEXIAMAction.ARCHIVE
}