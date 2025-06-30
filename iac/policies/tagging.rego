package system.main

# Require every provisioned resource to have an 'owner' tag.
# Assumes input structure for a resource like:
# {
#   "type": "any_resource_type",
#   "name": "my-resource-1",
#   "tags": {
#     "environment": "prod"
#     # Missing "owner" tag
#   }
# }
# Or for a resource that has the owner tag:
# {
#   "type": "another_resource_type",
#   "name": "my-resource-2",
#   "tags": {
#     "environment": "dev",
#     "owner": "team-alpha"
#   }
# }

violations[msg] {
    some i
    resource := input.resources[i]

    # Check if 'tags' field exists and if 'owner' tag is missing or empty
    not resource.tags.owner # True if 'owner' key doesn't exist
    # OR
    # resource.tags.owner == "" # Uncomment to also deny empty owner tags

    msg := {
        "policy_name": "tagging_policy_missing_owner",
        "message": sprintf("Resource '%s' of type '%s' must have an 'owner' tag.", [resource.name, resource.type]),
        "details": {
            "resource_name": resource.name,
            "resource_type": resource.type,
            "current_tags": resource.tags
        }
    }
}

# To also deny empty owner tags, you could modify the condition:
# violations[msg] {
#     some i
#     resource := input.resources[i]
#     reason := ""
#     if { not resource.tags.owner } {
#         reason := "tag is missing"
#     } else if { resource.tags.owner == "" } {
#         reason := "tag is present but empty"
#     }
#     reason != "" # If a reason was set, then it's a violation
#
#     msg := {
#         "policy_name": "tagging_policy_missing_owner",
#         "message": sprintf("Resource '%s' of type '%s' must have a non-empty 'owner' tag. Issue: %s.", [resource.name, resource.type, reason]),
#         "details": { ... }
#     }
# }
# For Phase 3, the simpler version (just checking for presence) is fine.
