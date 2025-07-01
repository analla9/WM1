from typing import List, Dict, Any, Optional, Union
from pydantic import BaseModel, Field, validator
import yaml

# --- Input Models ---
class BlueprintInput(BaseModel):
    name: str
    type: str # e.g., string, integer, boolean
    description: Optional[str] = None
    default: Optional[Any] = None
    # Could add more validation like 'required', 'pattern' for strings, 'min'/'max' for numbers

# --- Tier Models ---
class TierSource(BaseModel):
    git: Optional[str] = None
    path: Optional[str] = None
    branch: Optional[str] = None
    # Could also support other sources like local path, http URL for a tarball etc.

class Tier(BaseModel):
    name: str
    type: str # e.g., "terraform", "ansible", "plugin", "kubernetes-yaml"
    source: Optional[TierSource] = None
    variables: Optional[Dict[str, Any]] = Field(default_factory=dict)
    inventory: Optional[Dict[str, Any]] = None # Specific to ansible type

    @validator('inventory', always=True)
    def check_inventory_for_ansible(cls, v, values):
        if values.get('type') == 'ansible' and v is None:
            # Ansible tiers might not always need inventory (e.g. localhost)
            # but often do. For now, making it optional.
            # raise ValueError("Ansible type tier must have an inventory defined")
            pass
        if values.get('type') != 'ansible' and v is not None:
            raise ValueError("Inventory should only be defined for 'ansible' type tiers")
        return v

# --- Lifecycle Action Models ---
class LifecycleAction(BaseModel):
    name: str
    type: str # e.g., "plugin", "webhook", "ansible_playbook"
    plugin_name: Optional[str] = None # if type is plugin
    url: Optional[str] = None # if type is webhook
    playbook: Optional[str] = None # if type is ansible_playbook (path within source)
    inputs: Optional[Dict[str, Any]] = Field(default_factory=dict)
    payload: Optional[Dict[str, Any]] = Field(default_factory=dict) # if type is webhook

    @validator('plugin_name', always=True)
    def check_plugin_name(cls, v, values):
        if values.get('type') == 'plugin' and v is None:
            raise ValueError("Plugin type action must have a plugin_name")
        return v

    @validator('url', always=True)
    def check_url(cls, v, values):
        if values.get('type') == 'webhook' and v is None:
            raise ValueError("Webhook type action must have a url")
        return v

# --- Main Blueprint Schema Models ---
class BlueprintMetadata(BaseModel):
    name: str
    description: Optional[str] = None
    # Could add CMP-specific annotations or labels here

class BlueprintDependency(BaseModel):
    from_tier: str = Field(alias="from")
    to_tier: str = Field(alias="to")

    class Config:
        allow_population_by_field_name = True


class BlueprintSpec(BaseModel):
    inputs: List[BlueprintInput] = Field(default_factory=list)
    tiers: List[Tier] = Field(default_factory=list)
    dependencies: List[BlueprintDependency] = Field(default_factory=list)
    lifecycle_actions: Optional[Dict[str, List[LifecycleAction]]] = Field(default_factory=dict) # e.g., {"post_build": [...]}

    @validator('lifecycle_actions')
    def validate_lifecycle_hook_names(cls, v):
        valid_hooks = {"pre_build", "post_build", "pre_teardown", "post_teardown"}
        for hook_name in v.keys():
            if hook_name not in valid_hooks:
                raise ValueError(f"Invalid lifecycle hook name: {hook_name}. Must be one of {valid_hooks}")
        return v

class Blueprint(BaseModel):
    apiVersion: str # e.g., "cognitive-cmp.io/v1"
    kind: str # Should be "Blueprint"
    metadata: BlueprintMetadata
    spec: BlueprintSpec

    @validator('apiVersion')
    def check_api_version(cls, v):
        # Example: cognitive-cmp.io/v1 or similar
        if not v.startswith("cognitive-cmp.io/"): # Basic check
            raise ValueError("apiVersion must be in the format 'cognitive-cmp.io/vX'")
        return v

    @validator('kind')
    def check_kind(cls, v):
        if v != "Blueprint":
            raise ValueError("kind must be 'Blueprint'")
        return v


# Example Usage (for testing within this file if needed)
if __name__ == "__main__":
    sample_yaml_blueprint = """
apiVersion: cognitive-cmp.io/v1
kind: Blueprint
metadata:
  name: hybrid-webapp-prod
  description: A two-tier web application.
spec:
  inputs:
    - name: web_instance_size
      type: string
      description: "AWS EC2 instance size for the web servers."
      default: 't3.medium'
    - name: db_server_ip
      type: string
      description: "IP address of the on-premises KVM host for the database."
  tiers:
    - name: web-tier
      type: terraform
      source:
        git: https://github.com/my-org/tf-modules.git
        path: /aws-web-server
        branch: main
      variables:
        instance_type: ${{ inputs.web_instance_size }}
        vpc_id: "vpc-0123abcd"
    - name: db-tier
      type: ansible
      source:
        git: https://github.com/my-org/ansible-playbooks.git
        path: /mysql-onprem
      inventory:
        hosts:
          - ${{ inputs.db_server_ip }}
      variables:
        mysql_root_password: ${{ secrets.db_root_password }} # Example of secret interpolation
  dependencies:
    - from: db-tier # Blueprint uses 'from', Pydantic model uses 'from_tier' due to 'from' being a keyword
      to: web-tier
  lifecycle_actions:
    post_build:
      - name: "Register with DNS"
        type: plugin
        plugin_name: "infoblox-register-cname"
        inputs:
          hostname: "app.mycompany.com"
          target: ${{ tiers.web-tier.outputs.load_balancer_dns }} # Example of output interpolation
    pre_teardown:
      - name: "Notify monitoring system"
        type: webhook
        url: "https://monitoring.mycompany.com/api/v1/maintenance"
        payload:
          service: "webapp-prod"
          status: "decommissioning"
"""
    try:
        data = yaml.safe_load(sample_yaml_blueprint)
        # Manually handle 'from' to 'from_tier' for dependencies if direct parsing
        if 'spec' in data and 'dependencies' in data['spec']:
            for dep in data['spec']['dependencies']:
                if 'from' in dep:
                    dep['from_tier'] = dep.pop('from')

        blueprint_obj = Blueprint(**data)
        print("Blueprint parsed successfully!")
        print(blueprint_obj.json(indent=2, by_alias=True))

        # Test invalid lifecycle hook
        invalid_lifecycle_yaml = sample_yaml_blueprint.replace("post_build", "after_build")
        data_invalid = yaml.safe_load(invalid_lifecycle_yaml)
        # Blueprint(**data_invalid) # This should raise a ValueError

    except yaml.YAMLError as e:
        print(f"YAML Error: {e}")
    except Exception as e: # Catches Pydantic ValidationErrors
        print(f"Validation Error: {e}")

    # Example of how to handle 'from' keyword in dependencies when loading:
    # data = yaml.safe_load(yaml_string)
    # if 'spec' in data and 'dependencies' in data['spec']:
    #     for dep_data in data['spec']['dependencies']:
    #         if 'from' in dep_data:
    #             dep_data['from_tier'] = dep_data.pop('from')
    # bp = Blueprint(**data)
    # This manual step is needed because Pydantic's `by_alias` works for dumping,
    # but aliases are not automatically used for parsing field names that are Python keywords.
    # A custom root_validator or pre-processing the dict could also handle this.
    # For the API endpoint, we'll parse to dict first, then do this transformation.
    pass
