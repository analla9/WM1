from typing import List, Optional, Dict, Any
from uuid import UUID, uuid4
from pydantic import BaseModel, Field
from .enums import ProviderType, NetworkInterfaceType

class CanonicalNetworkInterface(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    name: Optional[str] = None # e.g., eth0
    mac_address: Optional[str] = None
    ip_addresses: List[str] = Field(default_factory=list) # Can have multiple IPs (IPv4, IPv6)
    network_name: Optional[str] = None # Name of the network it's connected to (e.g., KVM bridge name, OpenStack network name)
    interface_type: Optional[NetworkInterfaceType] = NetworkInterfaceType.OTHER # e.g., virtio, e1000
    provider_specific: Dict[str, Any] = Field(default_factory=dict) # e.g., KVM bridge, OpenStack port ID

class CanonicalNetwork(BaseModel):
    id: UUID = Field(default_factory=uuid4) # Internal CMP ID
    name: str
    cidr_block: Optional[str] = None
    provider_id: Optional[str] = None # The unique ID from the source provider (e.g., AWS VPC ID, OpenStack Network ID)
    provider_type: ProviderType
    region: Optional[str] = None
    is_default: bool = False
    tags: Dict[str, str] = Field(default_factory=dict)
    provider_specific_config: Dict[str, Any] = Field(default_factory=dict) # Store provider-native configuration

    class Config:
        use_enum_values = True
