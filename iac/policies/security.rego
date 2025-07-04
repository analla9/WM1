package system.main

violations[{"policy_name": "security_policy_s3_public_read", "message": msg}] if {
    some i
    resource := input.resources[i]
    resource.type == "aws_s3_bucket"
    resource.properties.acl == "public-read" # Assuming properties.acl structure
    msg := sprintf("S3 bucket '%s' must not have public read access (acl: 'public-read').", [resource.name])
}
