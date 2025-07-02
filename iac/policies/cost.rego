package system.main # All policies in the same package for simplicity, or use sub-packages
# Corrected cost.rego

# Deny if a resource is a p5.48xlarge instance in a non-production environment.
violations[{"policy_name": "cost_policy_expensive_instance", "message": msg, "details": {"resource_name": resource.name, "instance_type": resource.instance_type}}] if {
    some i
    resource := input.resources[i]
    resource.type == "aws_instance"
    resource.instance_type == "p5.48xlarge"
    lower(input.project_context.environment_type) != "production"
    msg := sprintf("Instance type '%s' is not allowed for resource '%s' in a non-production environment.", [resource.instance_type, resource.name])
}

# Deny expensive instance types in non-production environments
# Assumes input structure like:
# {
#   "resources": [
#     {"type": "aws_instance", "instance_type": "p5.48xlarge", "tags": {"environment": "dev"}},
#     {"type": "aws_instance", "instance_type": "t3.micro", "tags": {"environment": "prod"}}
#   ],
#   "project_context": {"environment_type": "non-production"} # Or get from resource tags
# }
# For Phase 3, the mock plan from orchestration worker will define this structure.

default expensive_instance_types = {"p5.48xlarge", "m5.24xlarge", "c5.18xlarge", "x1e.32xlarge"}
default non_production_environments = {"dev", "qa", "staging", "test", "non-production", "nonprod"}

# Rule to generate violation messages
violations[msg] {
    some i
    resource := input.resources[i]
    resource.type == "aws_instance" # Example for AWS, adapt for other providers or canonical types

    # Check if the resource's environment is non-production
    # Option 1: Based on a global project context
    # lower(input.project_context.environment_type) # in non_production_environments
    # Option 2: Based on resource tags (more flexible)
    resource_env_tag := lower(resource.tags.environment) # Assuming tags.environment exists
    non_production_environments[resource_env_tag]

    # Check if the instance type is in the expensive list
    expensive_instance_types[resource.instance_type]

    # Construct the violation message
    msg := {
        "policy_name": "cost_policy_expensive_instance",
        "message": sprintf("Expensive instance type '%s' is not allowed for resource '%s' in non-production environment '%s'.", [resource.instance_type, resource.name, resource_env_tag]),
        "details": {
            "resource_name": resource.name,
            "instance_type": resource.instance_type,
            "environment_tag": resource_env_tag
        }
    }
}

# If no violations are found by any policy, this 'violations' rule will be undefined (not an empty set).
# The governance engine should check if 'violations' is defined and non-empty in OPA's response.
# If OPA_DECISION_PATH is set to /v1/data/system/main/violations, OPA will return the set of messages.
# If the set is empty or 'violations' is undefined in the response, it means no violations.
# OPA by default returns "undefined" if a rule doesn't produce any results.
# If you want an empty list [] when no violations, you can add:
# violations := [] if { count(all_violations) == 0 }
# all_violations = { m | m := violations[_] } # This is getting circular.
# Better to let governance engine handle undefined/empty 'result' from OPA.

# Helper: ensure input structure for tags exists to prevent runtime errors
# This isn't strictly necessary if the input is guaranteed, but good practice.
# is_non_production_resource(resource) {
#    resource.tags
#    lower(resource.tags.environment) # in non_production_environments
# }
