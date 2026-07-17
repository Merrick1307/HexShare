from fastapi import Request


def get_document_service(request: Request):
    return request.app.state.document_service


def get_document_group_service(request: Request):
    return request.app.state.document_group_service


def get_link_service(request: Request):
    return request.app.state.link_service


def get_analytics_service(request: Request):
    return request.app.state.analytics_service


def get_upload_service(request: Request):
    return request.app.state.upload_service


def get_viewer_service(request: Request):
    return request.app.state.viewer_service


def get_nda_service(request: Request):
    return request.app.state.nda_service


def get_storage(request: Request):
    return request.app.state.storage


def get_external_room_access_service(request: Request):
    return request.app.state.external_room_access_service


def get_external_room_viewer_service(request: Request):
    return request.app.state.external_room_viewer_service


def get_object_storage(request: Request):
    return request.app.state.object_storage


def get_access_control(request: Request):
    return request.app.state.access_control


def get_tenant_auth(request: Request):
    return request.app.state.tenant_auth


def get_share_auth(request: Request):
    return request.app.state.share_auth


def get_external_room_auth(request: Request):
    return request.app.state.external_room_auth


def get_oidc_client_service(request: Request):
    return request.app.state.oidc_client_service


def get_iam_policy(request: Request):
    return request.app.state.iam_policy


def get_email_adapter(request: Request):
    return request.app.state.email_adapter


def get_template_loader(request: Request):
    return request.app.state.template_loader


def get_event_dispatcher(request: Request):
    return request.app.state.event_dispatcher


def get_policy_loader(request: Request):
    return getattr(request.app.state, "policy_loader", None)


def get_rate_limit_backend(request: Request):
    return getattr(request.app.state, "rate_limit_backend", None)
