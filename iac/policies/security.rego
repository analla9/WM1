package system.main

# Deny creation of S3 buckets with public read ACL
# Assumes input structure for a resource like:
# {
#   "type": "aws_s3_bucket",
#   "name": "my-public-bucket",
#   "properties": {
#     "acl": "public-read" # or "public-read-write"
#   }
# }

violations[msg] {
    some i
    resource := input.resources[i]
    resource.type == "aws_s3_bucket" # Example for AWS S3

    # Check for public ACLs
    public_acls := {"public-read", "public-read-write", "authenticated-read"} # Add other relevant public ACLs
    resource_acl := lower(resource.properties.acl)
    public_acls[resource_acl]

    msg := {
        "policy_name": "security_policy_s3_public_acl",
        "message": sprintf("S3 bucket '%s' must not have a public ACL ('%s'). Found '%s'.", [resource.name, resource_acl, resource_acl]),
        "details": {
            "resource_name": resource.name,
            "acl_configured": resource_acl
        }
    }
}

# Note: A more comprehensive S3 policy would also check bucket policies,
# Block Public Access settings, etc. This is a simplified example for Phase 3.
