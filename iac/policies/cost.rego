package system.main

violations[{"policy_name": "cost_policy_expensive_instance", "message": msg}] if {
    some i
    resource := input.resources[i]
    resource.type == "aws_instance"
    resource.instance_type == "p5.48xlarge" # Corrected based on original user intent, not the example's list
    lower(input.project_context.environment_type) != "production" # Assuming project_context is available in input
    msg := sprintf("Instance type '%s' is not allowed in a non-production environment for resource '%s'.", [resource.instance_type, resource.name]) # Added resource name to msg
}
