# Corrected tagging.rego
package system.main

# Deny if a resource does not have an 'owner' tag.
violations[{"policy_name": "tagging_policy_missing_owner", "message": msg, "details": {"resource_name": resource.name}}] if {
    some i
    resource := input.resources[i]
    not resource.tags.owner
    msg := sprintf("Resource '%s' is missing the mandatory 'owner' tag.", [resource.name])
}
