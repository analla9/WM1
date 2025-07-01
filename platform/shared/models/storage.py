from typing import Optional, Dict, Any
from uuid import UUID, uuid4
from pydantic import BaseModel, Field
from .enums import StorageType, ProviderType

class CanonicalStorageDisk(BaseModel): # Helper model for disks within CanonicalCompute
    name: str # e.g., vda, sdb
    size_gb: int
    path: Optional[str] = None # Path to the disk image or device
    disk_type: Optional[str] = None # e.g., qcow2, raw, ssd, hdd
    is_boot_disk: bool = False
    provider_specific: Dict[str, Any] = Field(default_factory=dict)


class CanonicalStorage(BaseModel):
    id: UUID = Field(default_factory=uuid4) # Internal CMP ID
    name: str
    size_gb: int
    storage_type: StorageType = Field(alias="type") # Using alias to match blueprint 'type' field
    iops: Optional[int] = None # Optional, for provisioned IOPS volumes
    throughput_mbps: Optional[int] = None # Optional, for provisioned throughput
    provider_id: Optional[str] = None # The unique ID from the source provider (e.g., AWS EBS Volume ID)
    provider_type: ProviderType
    region: Optional[str] = None
    attached_to_vm_id: Optional[str] = None # Provider ID of the VM it's attached to
    attachment_path: Optional[str] = None # e.g. /dev/sdf
    tags: Dict[str, str] = Field(default_factory=dict)
    provider_specific_config: Dict[str, Any] = Field(default_factory=dict)

    class Config:
        use_enum_values = True
        allow_population_by_field_name = True # Allows using 'type' in input data for storage_type
