from typing import List, Optional, Dict, Any
from uuid import UUID, uuid4
from pydantic import BaseModel, Field

from .network import CanonicalNetworkInterface
from .storage import CanonicalStorageDisk # Re-using for disks attached to compute
from .enums import ResourceState, ProviderType

class CanonicalCompute(BaseModel):
    id: UUID = Field(default_factory=uuid4) # Internal CMP ID
    name: str
    state: ResourceState
    cpu_cores: int
    memory_mb: int
    disks: List[CanonicalStorageDisk] = Field(default_factory=list)
    nics: List[CanonicalNetworkInterface] = Field(default_factory=list)

    provider_id: str # The unique ID from the source provider (e.g., AWS Instance ID, OpenStack VM UUID, KVM domain UUID)
    provider_type: ProviderType

    hostname: Optional[str] = None
    region: Optional[str] = None # e.g., us-east-1 for AWS, or KVM host identifier
    zone: Optional[str] = None # e.g., us-east-1a for AWS

    image_id: Optional[str] = None # ID of the image/template used
    instance_type_family: Optional[str] = None # e.g. t3, m5 for AWS; KVM custom

    created_at: Optional[str] = None # Timestamp of creation on provider
    tags: Dict[str, str] = Field(default_factory=dict)

    # Stores provider-native configuration like AWS Launch Template ID, KVM XML definition aspects
    provider_specific_config: Dict[str, Any] = Field(default_factory=dict)

    class Config:
        use_enum_values = True # Ensures enum values are used in serialization (e.g., "RUNNING" instead of ResourceState.RUNNING)
