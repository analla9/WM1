from enum import Enum

class ResourceState(str, Enum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    STOPPED = "STOPPED"
    TERMINATED = "TERMINATED" # Equivalent to KVM's SHUTOFF if permanent
    SUSPENDED = "SUSPENDED"   # Equivalent to KVM's PAUSED
    ERROR = "ERROR"
    UNKNOWN = "UNKNOWN"
    # KVM specific states to map from:
    # VIR_DOMAIN_NOSTATE = 0 (NOSTATE) -> UNKNOWN or PENDING initially
    # VIR_DOMAIN_RUNNING = 1 (RUNNING) -> RUNNING
    # VIR_DOMAIN_BLOCKED = 2 (BLOCKED) -> RUNNING (still active, but blocked on resource)
    # VIR_DOMAIN_PAUSED = 3 (PAUSED) -> SUSPENDED
    # VIR_DOMAIN_SHUTDOWN = 4 (SHUTDOWN) -> STOPPED (being shut down)
    # VIR_DOMAIN_SHUTOFF = 5 (SHUTOFF) -> TERMINATED or STOPPED (if it can be restarted)
    # VIR_DOMAIN_CRASHED = 6 (CRASHED) -> ERROR
    # VIR_DOMAIN_PMSUSPENDED = 7 (PMSUSPENDED) -> SUSPENDED

class ProviderType(str, Enum):
    AWS = "AWS"
    GCP = "GCP"
    AZURE = "AZURE" # Not explicitly in blueprint text, but good to have
    OPENSTACK = "OPENSTACK"
    KVM = "KVM"
    VMWARE = "VMWARE" # Not explicitly in blueprint text
    OTHER = "OTHER"

class StorageType(str, Enum):
    BLOCK = "BLOCK"
    OBJECT = "OBJECT"
    FILE = "FILE"
    UNKNOWN = "UNKNOWN"

class NetworkInterfaceType(str, Enum): # Added for more clarity on NICs
    VIRTIO = "VIRTIO"
    E1000 = "E1000"
    VMXNET3 = "VMXNET3"
    OTHER = "OTHER"
