# Corrected security.rego
package system.main

# Deny if an S3 bucket has public read access.
violations[{"policy_name": "security_policy_s3_public_read", "message": msg, "details": {"resource_name": resource.name}}] if {
    some i
    resource := input.resources[i]
    resource.type == "aws_s3_bucket"
    resource.properties.acl == "public-read"
    msg := sprintf("S3 bucket '%s' must not have public read access.", [resource.name])
}
