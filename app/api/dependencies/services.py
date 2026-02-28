from fastapi import Request

def get_document_service(request: Request):
    return request.app.state.document_service

def get_link_service(request: Request):
    return request.app.state.link_service

def get_analytics_service(request: Request):
    return request.app.state.analytics_service

def get_access_control(request: Request):
    return request.app.state.access_control

def get_tenant_auth(request: Request):
    return request.app.state.tenant_auth

def get_share_auth(request: Request):
    return request.app.state.share_auth