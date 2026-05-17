"""
Port interfaces for HexShare.

These abstract classes define the operations that HexShare services
depend on.  Ports allow the core application to remain independent of
concrete infrastructure and facilitate testing by enabling in-memory
or mock implementations.
"""

from .storage_port import StoragePort
from .token_port import TokenPort
from .event_bus_port import EventBusPort
from .rendered_page_cache_port import RenderedPageCachePort
from .task_queue_port import TaskQueuePort
from .object_storage_port import (
    ObjectDescriptor,
    ObjectInfo,
    ObjectStoragePort,
    ObjectWriteRequest,
    PresignedUpload,
    TemporaryObjectAccess,
)

__all__ = [
    "StoragePort",
    "TokenPort",
    "EventBusPort",
    "RenderedPageCachePort",
    "TaskQueuePort",
    "ObjectStoragePort",
    "TemporaryObjectAccess",
    "PresignedUpload",
    "ObjectDescriptor",
    "ObjectInfo",
    "ObjectWriteRequest",
]
