import libvirt
import os
import logging
import time
import json
import schedule
from typing import List, Dict, Any, Optional
from uuid import UUID

from kafka import KafkaProducer
from kafka.errors import KafkaError
from dotenv import load_dotenv

# Assuming models are structured like this, adjust if necessary
# This relative import path might need adjustment based on how the PYTHONPATH is set in Docker
# For simplicity, let's assume these models might be copied or made available to the connector.
# A better way would be to package 'shared' and install it.
# For now, we will define them here or expect them to be in PYTHONPATH.
# To make this work without complex packaging for Phase 2, we can temporarily
# copy the models or use a symlink in the Dockerfile if running locally.
# For a cleaner approach, these models should be an installable package.
# For now, let's assume they are accessible. This might require path adjustments later.
try:
    from platform.shared.models.compute import CanonicalCompute
    from platform.shared.models.storage import CanonicalStorageDisk
    from platform.shared.models.network import CanonicalNetworkInterface
    from platform.shared.models.enums import ResourceState, ProviderType, NetworkInterfaceType
except ImportError:
    # This is a fallback for environments where platform.shared is not directly in PYTHONPATH
    # You'd typically solve this with a proper Python package structure and installation.
    # For this phase, we'll log an error and define simplified versions if not found,
    # or rely on Docker PYTHONPATH setup.
    logging.error("Could not import shared models directly. Ensure PYTHONPATH is set up correctly or models are available.")
    # Simplified local definitions as a last resort for this specific file to run,
    # but the goal is to use the shared ones.
    from enum import Enum
    from pydantic import BaseModel, Field
    from uuid import uuid4

    class ResourceState(str, Enum):
        PENDING = "PENDING"; RUNNING = "RUNNING"; STOPPED = "STOPPED"; TERMINATED = "TERMINATED"
        SUSPENDED = "SUSPENDED"; ERROR = "ERROR"; UNKNOWN = "UNKNOWN"
    class ProviderType(str, Enum): KVM = "KVM"
    class NetworkInterfaceType(str, Enum): VIRTIO = "VIRTIO"; E1000 = "E1000"; OTHER = "OTHER"

    class CanonicalNetworkInterface(BaseModel):
        id: UUID = Field(default_factory=uuid4); name: Optional[str] = None; mac_address: Optional[str] = None
        ip_addresses: List[str] = Field(default_factory=list); network_name: Optional[str] = None
        interface_type: Optional[NetworkInterfaceType] = NetworkInterfaceType.OTHER; provider_specific: Dict[str, Any] = Field(default_factory=dict)
    class CanonicalStorageDisk(BaseModel):
        name: str; size_gb: int; path: Optional[str] = None; disk_type: Optional[str] = None
        is_boot_disk: bool = False; provider_specific: Dict[str, Any] = Field(default_factory=dict)
    class CanonicalCompute(BaseModel):
        id: UUID = Field(default_factory=uuid4); name: str; state: ResourceState; cpu_cores: int
        memory_mb: int; disks: List[CanonicalStorageDisk] = Field(default_factory=list)
        nics: List[CanonicalNetworkInterface] = Field(default_factory=list); provider_id: str
        provider_type: ProviderType = ProviderType.KVM; hostname: Optional[str] = None; region: Optional[str] = None
        zone: Optional[str] = None; image_id: Optional[str] = None; instance_type_family: Optional[str] = None
        created_at: Optional[str] = None; tags: Dict[str, str] = Field(default_factory=dict)
        provider_specific_config: Dict[str, Any] = Field(default_factory=dict)
        class Config: use_enum_values = True


# Load environment variables
load_dotenv()

# Logging Configuration
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(module)s - %(message)s')
logger = logging.getLogger(__name__)

# KVM & Kafka Configuration
LIBVIRT_URI = os.getenv("LIBVIRT_URI", "qemu:///system") # Default for system-wide libvirtd
KAFKA_BOOTSTRAP_SERVERS = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "kafka:9092").split(',')
KAFKA_DISCOVERY_TOPIC = "discovery.resource.updates"
DISCOVERY_INTERVAL_SECONDS = int(os.getenv("DISCOVERY_INTERVAL_SECONDS", 300)) # 5 minutes

# Global Kafka Producer
producer = None

def initialize_kafka_producer():
    global producer
    try:
        producer = KafkaProducer(
            bootstrap_servers=KAFKA_BOOTSTRAP_SERVERS,
            value_serializer=lambda v: json.dumps(v).encode('utf-8'),
            retries=5,
            acks='all'
        )
        logger.info(f"Successfully connected to Kafka at {KAFKA_BOOTSTRAP_SERVERS}")
    except KafkaError as e:
        logger.error(f"Failed to initialize Kafka producer: {e}")
        producer = None

def map_kvm_state_to_canonical(kvm_state_code: int) -> ResourceState:
    # Based on libvirt domain states:
    # VIR_DOMAIN_NOSTATE = 0
    # VIR_DOMAIN_RUNNING = 1
    # VIR_DOMAIN_BLOCKED = 2 (Still running, but I/O blocked)
    # VIR_DOMAIN_PAUSED = 3
    # VIR_DOMAIN_SHUTDOWN = 4 (Being shut down)
    # VIR_DOMAIN_SHUTOFF = 5 (Powered off)
    # VIR_DOMAIN_CRASHED = 6
    # VIR_DOMAIN_PMSUSPENDED = 7
    state_map = {
        libvirt.VIR_DOMAIN_NOSTATE: ResourceState.UNKNOWN,
        libvirt.VIR_DOMAIN_RUNNING: ResourceState.RUNNING,
        libvirt.VIR_DOMAIN_BLOCKED: ResourceState.RUNNING, # Or a custom 'BLOCKED' state if needed
        libvirt.VIR_DOMAIN_PAUSED: ResourceState.SUSPENDED,
        libvirt.VIR_DOMAIN_SHUTDOWN: ResourceState.STOPPED, # Or a custom 'SHUTTING_DOWN'
        libvirt.VIR_DOMAIN_SHUTOFF: ResourceState.TERMINATED, # Assuming shutoff means it won't come back unless started
        libvirt.VIR_DOMAIN_CRASHED: ResourceState.ERROR,
        libvirt.VIR_DOMAIN_PMSUSPENDED: ResourceState.SUSPENDED,
    }
    return state_map.get(kvm_state_code, ResourceState.UNKNOWN)

def get_domain_ip_address(domain) -> List[str]:
    ips = []
    try:
        ifaces = domain.interfaceAddresses(libvirt.VIR_DOMAIN_INTERFACE_ADDRESSES_SRC_AGENT, 0)
        if ifaces:
            for (_name, val) in ifaces.items():
                if val['addrs']:
                    for addr in val['addrs']:
                        if addr['type'] == libvirt.VIR_IP_ADDR_TYPE_IPV4: # or IPV6
                            ips.append(addr['addr'])
    except libvirt.libvirtError as e:
        logger.debug(f"Could not get IP for domain {domain.name()} via guest agent: {e}. Try lease if available.")
        try:
            ifaces = domain.interfaceAddresses(libvirt.VIR_DOMAIN_INTERFACE_ADDRESSES_SRC_LEASE, 0)
            if ifaces:
                for (_name, val) in ifaces.items():
                    if val['addrs']:
                        for addr in val['addrs']:
                            if addr['type'] == libvirt.VIR_IP_ADDR_TYPE_IPV4:
                                ips.append(addr['addr'])
        except libvirt.libvirtError as e_lease:
             logger.debug(f"Could not get IP for domain {domain.name()} via lease: {e_lease}")
    return list(set(ips)) # Unique IPs

def discover_kvm_vms():
    logger.info(f"Starting KVM VM discovery from {LIBVIRT_URI}...")
    if not producer:
        logger.error("Kafka producer not initialized. Skipping discovery.")
        initialize_kafka_producer() # Try to re-initialize
        if not producer:
            return

    conn = None
    try:
        conn = libvirt.open(LIBVIRT_URI)
    except libvirt.libvirtError as e:
        logger.error(f"Failed to connect to libvirt at {LIBVIRT_URI}: {e}")
        return

    if conn is None:
        logger.error(f"Failed to open connection to libvirt driver: {LIBVIRT_URI}")
        return

    discovered_vms = 0
    try:
        # List all defined domains (active and inactive)
        # domains = conn.listAllDomains(0)
        # Or, list only active domains:
        domainIDs = conn.listDomainsID()
        active_domains = [conn.lookupByID(id) for id in domainIDs]

        for domain in active_domains: # Or iterate through conn.listAllDomains(0)
            if not domain.isActive(): # Ensure we only process running or relevant VMs
                # If using listAllDomains, you might want to skip non-active ones or map their state.
                # continue
                pass

            info = domain.info() # Returns [state, maxMem, memory, nbVirtCPU, cpuTime]
            state_code = info[0]

            # Disks
            disks_info: List[CanonicalStorageDisk] = []
            try:
                # This part requires parsing the domain XML to get disk details
                # as libvirt's direct disk info is limited.
                from xml.etree import ElementTree
                xml_desc = domain.XMLDesc(0)
                root = ElementTree.fromstring(xml_desc)
                for disk_el in root.findall('.//devices/disk'):
                    device_type = disk_el.get('device') # disk, cdrom, floppy, lun
                    if device_type != 'disk' and device_type != 'lun': # Only interested in actual storage disks
                        continue

                    target_el = disk_el.find('target')
                    dev_name = target_el.get('dev') if target_el is not None else None # e.g., vda, hda

                    source_el = disk_el.find('source')
                    disk_path = None
                    if source_el is not None:
                        if source_el.get('file'):
                            disk_path = source_el.get('file')
                        elif source_el.get('dev'):
                            disk_path = source_el.get('dev')
                        elif source_el.get('protocol'): # for iscsi, nfs etc.
                            disk_path = f"{source_el.get('protocol')}:{source_el.get('name')}"


                    # Getting disk size is tricky without qemu-img or looking up backing file
                    # For simplicity, we'll omit actual size for now or require guest agent
                    # This is a known complexity in libvirt generic parsing.
                    # Actual size would require 'domain.blockInfo(disk_path)' or 'domain.blockStats(dev_name)'
                    # but these might not always give capacity, rather allocation.
                    # For now, placeholder size.
                    disk_size_gb = 0 # Placeholder
                    try:
                        if dev_name: # or disk_path if it's a file
                             # this gets current allocation, not capacity for files
                            block_info = domain.blockInfo(dev_name, 0) # or disk_path
                            disk_size_gb = block_info[0] // (1024**3) # Capacity in GB
                    except libvirt.libvirtError:
                        logger.debug(f"Could not get block info for {dev_name} on {domain.name()}")


                    disks_info.append(CanonicalStorageDisk(
                        name=dev_name or "unknown_disk",
                        size_gb=disk_size_gb, # This is often allocation, not capacity for qcow2
                        path=disk_path,
                        disk_type=disk_el.find('driver').get('type') if disk_el.find('driver') is not None else None, # e.g. qcow2, raw
                        is_boot_disk=(disk_el.find('boot') is not None and disk_el.find('boot').get('order') == '1') # Basic check
                    ))
            except Exception as e_disk:
                logger.error(f"Error parsing disk info for {domain.name()}: {e_disk}")


            # Network Interfaces
            nics_info: List[CanonicalNetworkInterface] = []
            try:
                from xml.etree import ElementTree
                xml_desc = domain.XMLDesc(0)
                root = ElementTree.fromstring(xml_desc)
                domain_ips = get_domain_ip_address(domain) # Get all IPs once
                ip_idx = 0

                for iface_el in root.findall('.//devices/interface'):
                    mac_el = iface_el.find('mac')
                    mac_address = mac_el.get('address') if mac_el is not None else None

                    target_el = iface_el.find('target')
                    if_name = target_el.get('dev') if target_el is not None else None # This is the host-side tap device, not guest ifname

                    source_el = iface_el.find('source')
                    network_name = None
                    if source_el is not None:
                        if source_el.get('network'):
                            network_name = source_el.get('network') # KVM network name
                        elif source_el.get('bridge'):
                            network_name = source_el.get('bridge') # Host bridge name

                    model_el = iface_el.find('model')
                    if_type_str = model_el.get('type') if model_el is not None else NetworkInterfaceType.OTHER.value
                    try:
                        if_type = NetworkInterfaceType(if_type_str)
                    except ValueError:
                        if_type = NetworkInterfaceType.OTHER

                    # Simplistic IP assignment from list, not ideal but works for single NIC VMs
                    current_nic_ips = []
                    if domain_ips and ip_idx < len(domain_ips): # Assign first IP to first NIC etc.
                        current_nic_ips.append(domain_ips[ip_idx])
                        ip_idx +=1

                    nics_info.append(CanonicalNetworkInterface(
                        name=if_name, # Or guest interface name if available via agent
                        mac_address=mac_address,
                        ip_addresses=current_nic_ips,
                        network_name=network_name,
                        interface_type=if_type
                    ))
            except Exception as e_nic:
                logger.error(f"Error parsing NIC info for {domain.name()}: {e_nic}")

            canonical_vm = CanonicalCompute(
                # id: will be generated by Pydantic default_factory
                name=domain.name(),
                state=map_kvm_state_to_canonical(state_code),
                cpu_cores=info[3], # Number of virtual CPUs
                memory_mb=info[1] // 1024, # Max memory in MB
                disks=disks_info,
                nics=nics_info,
                provider_id=domain.UUIDString(),
                provider_type=ProviderType.KVM,
                hostname=domain.name(), # KVM domains usually don't have a separate hostname property from name
                region=conn.getHostname(), # Use KVM host as region for now
                # zone: N/A for standalone KVM
                # image_id: Hard to get reliably without parsing XML for backing file
                instance_type_family="custom", # KVM instances are custom
                # created_at: Not directly available, could use file mtime of XML or image
                tags={"source_uri": LIBVIRT_URI}, # Basic tagging
                provider_specific_config={
                    "memory_current_kb": info[2],
                    "cpu_time_ns": info[4],
                    "libvirt_xml_snippet": domain.XMLDesc(0)[:500] + "..." # Example, could be full XML
                }
            )

            # Publish to Kafka
            try:
                future = producer.send(KAFKA_DISCOVERY_TOPIC, value=canonical_vm.dict(by_alias=True))
                record_metadata = future.get(timeout=10)
                logger.info(f"Published VM '{canonical_vm.name}' (ID: {canonical_vm.provider_id}) to Kafka topic '{KAFKA_DISCOVERY_TOPIC}' at offset {record_metadata.offset}.")
                discovered_vms += 1
            except KafkaError as e:
                logger.error(f"Failed to send VM '{canonical_vm.name}' to Kafka: {e}")
            except Exception as e:
                logger.error(f"An unexpected error occurred while sending VM '{canonical_vm.name}' to Kafka: {e}")

    except libvirt.libvirtError as e:
        logger.error(f"Libvirt error during VM discovery: {e}")
    except Exception as e:
        logger.error(f"Unexpected error during VM discovery: {e}", exc_info=True)
    finally:
        if conn:
            conn.close()
            logger.debug("Closed libvirt connection.")

    logger.info(f"KVM VM discovery run complete. Discovered and published {discovered_vms} VMs.")


def main():
    logger.info("KVM Connector Service starting...")
    initialize_kafka_producer()

    # Perform an initial discovery on startup
    discover_kvm_vms()

    # Schedule periodic discovery
    # Note: schedule library is simple and runs in the main thread.
    # For more robust scheduling in a long-running service, consider APScheduler or a separate cron job.
    schedule.every(DISCOVERY_INTERVAL_SECONDS).seconds.do(discover_kvm_vms)
    logger.info(f"Scheduled KVM VM discovery every {DISCOVERY_INTERVAL_SECONDS} seconds.")

    while True:
        schedule.run_pending()
        time.sleep(1)

if __name__ == "__main__":
    # Ensure platform.shared is in PYTHONPATH if running directly
    # For example, by setting PYTHONPATH=$PYTHONPATH:../../.. when in platform/connectors/kvm-connector
    # This is mainly for local testing outside Docker. Dockerfile should handle Python path.

    # Check if shared models are accessible
    try:
        from platform.shared.models.compute import CanonicalCompute
        logger.info("Successfully accessed shared models.")
    except ImportError:
        logger.warning("Running with simplified local models. This is not ideal for production. Ensure 'platform.shared' is a proper package or in PYTHONPATH.")

    main()
