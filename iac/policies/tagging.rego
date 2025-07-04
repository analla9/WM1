package system.main

violations[{"policy_name": "tagging_policy_missing_owner", "message": msg}] if {
    some i
    resource := input.resources[i]
    not resource.tags.owner # Checks if 'owner' key is missing or its value is falsy (e.g. null, empty string, false)
    msg := sprintf("Resource '%s' (type: '%s') is missing the mandatory 'owner' tag or it is empty.", [resource.name, resource.type])
}
