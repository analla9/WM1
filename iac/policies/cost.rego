# Corrected cost.rego
package system.main

# Deny if a resource is a p5.48xlarge instance in a non-production environment.
violations[{"policy_name": "cost_policy_expensive_instance", "message": msg, "details": {"resource_name": resource.name, "instance_type": resource.instance_type}}] if {
    some i
    resource := input.resources[i]
    resource.type == "aws_instance"
    resource.instance_type == "p5.48xlarge"
    lower(input.project_context.environment_type) != "production"
    msg := sprintf("Instance type '%s' is not allowed for resource '%s' in a non-production environment.", [resource.instance_type, resource.name])
}
