"""Email notification integration guide.

This module provides a complete email notification system for HexShare.

## Architecture

    Domain Events (EventBusPort)
             ↓
    Event Dispatcher
             ↓
    Event Listeners (NdaEventListener, DocumentEventListener)
             ↓
    Email Notification Port
             ↓
    Adapters (SmtpEmailAdapter, TransactionalEmailAdapter, NoopEmailAdapter)

## Configuration

### SMTP (FastMail)
Set environment variables:
    - SMTP_HOST: smtp.fastmail.com
    - SMTP_PORT: 587
    - SMTP_USER: your-email@fastmail.com
    - SMTP_PASSWORD: your-app-password
    - SMTP_FROM_EMAIL: noreply@hexshare.example.com
    - SMTP_FROM_NAME: HexShare

### Transactional (SendByte)
Set environment variables:
    - EMAIL_PROVIDER: sendbyte
    - SENDBYTE_API_KEY: your-api-key
    - SENDBYTE_API_URL: https://api.sendbyte.com/v1
    - SENDBYTE_FROM_EMAIL: noreply@hexshare.example.com
    - SENDBYTE_FROM_NAME: HexShare

### Adding a New Provider
1. Create a new client in `app/adapters/email/clients/`
2. Extend `EmailClient` base class
3. Implement `send_email()` and `send_bulk_email()`
4. Handle provider-specific API differences in the client
5. Register in `TransactionalEmailAdapter._create_client_from_env()`
6. Update environment variable documentation

Example:
```python
# app/adapters/email/clients/myprovider_client.py
class MyProviderClient(EmailClient):
    def __init__(self, api_key=None, ...):
        self.api_key = api_key or os.getenv("MYPROVIDER_API_KEY")
        ...
    
    async def send_email(self, message):
        # Implement provider-specific logic
        ...
```

## Usage

In your dependency injection / main.py:

    from app.adapters.email import TransactionalEmailAdapter
    from app.adapters.event_dispatcher import EventDispatcher

    # Create email adapter (auto-detects provider from EMAIL_PROVIDER env var)
    email_service = TransactionalEmailAdapter()

    # Or explicitly pass a client:
    from app.adapters.email.clients import SendByteClient
    email_service = TransactionalEmailAdapter(client=SendByteClient())

    # Create event dispatcher
    event_dispatcher = EventDispatcher(event_bus, email_service)

    # When events are published:
    await event_bus.publish_event(
        tenant_id="tenant-123",
        event_name="nda.created",
        payload={
            "nda_id": "nda-456",
            "title": "NDA Agreement 2024",
            "created_by_email": "admin@company.com",
            "admin_emails": ["admin@company.com"]
        }
    )

    # Dispatch to listeners:
    await event_dispatcher.dispatch(
        event_name="nda.created",
        tenant_id="tenant-123",
        payload={...}
    )

## Supported Events

### NDA Events
- nda.created: New NDA created
- nda.acceptance_required: NDA requires user acceptance
- nda.accepted: User accepted NDA
- nda.rejected: User rejected NDA

### Document Events
- document.shared: Document shared with user
- document.accessed: Document was viewed/accessed
- share_link.expired: Document share link expired

## Adding New Events

1. Add handler method in relevant listener (NdaEventListener, DocumentEventListener, or new)
2. Register handler in EventDispatcher._register_handlers()
3. Emit event from domain service via EventBusPort
4. Dispatch event to listeners
"""
