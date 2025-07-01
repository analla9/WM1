-- Create a specific schema for the initial tenant or common objects.
-- For "Shared Database, Separate Schema", each tenant would get its own schema.
-- For Phase 1, we'll start with a 'public' schema or a dedicated 'aicmp_core' schema
-- and demonstrate the multi-tenant table structure within it.
-- The choice of public vs. a dedicated schema for common tables depends on strategy.
-- Let's use a common schema approach for now.

-- Note: In a true "Shared Database, Separate Schema" model, tenant-specific tables
-- would be created within a schema named after the tenant_id (e.g., tenant_abc.data_table).
-- The tables below are foundational and might live in a public/shared schema or be
-- replicated per tenant depending on the exact isolation requirements.
-- For Phase 1, we'll assume these are central tables.

-- The blueprint mentions "Shared Database, Separate Schema".
-- This means common tables like 'tenants' itself would be in a shared schema (e.g., public).
-- User-specific data or configurations that need strong isolation would go into tenant-specific schemas.
-- Let's define the core tables first, assuming they reside in the default 'public' schema or a common one.

-- Create Tenants Table
-- This table stores information about each tenant.
CREATE TABLE IF NOT EXISTS tenants (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name VARCHAR(255) NOT NULL UNIQUE,
    description TEXT,
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
    is_active BOOLEAN DEFAULT TRUE,
    -- For "Separate Schema" approach, we might store the schema name here
    schema_name VARCHAR(63) UNIQUE -- Max length for PostgreSQL identifiers
    -- Other tenant-specific configurations can be added here
);

-- Create Users Table
-- This table stores user information. Users will be associated with a tenant.
CREATE TABLE IF NOT EXISTS users (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL,
    username VARCHAR(255) NOT NULL, -- Should be unique within a tenant
    email VARCHAR(255) NOT NULL,    -- Should be unique globally or within a tenant, depending on policy
    hashed_password TEXT NOT NULL,
    first_name VARCHAR(100),
    last_name VARCHAR(100),
    is_active BOOLEAN DEFAULT TRUE,
    is_superuser BOOLEAN DEFAULT FALSE, -- For platform admins
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT fk_tenant
        FOREIGN KEY(tenant_id)
        REFERENCES tenants(id)
        ON DELETE CASCADE, -- If a tenant is deleted, its users are also deleted.

    UNIQUE (tenant_id, username), -- Username must be unique per tenant
    UNIQUE (tenant_id, email)     -- Email must be unique per tenant (common requirement)
    -- If email needs to be globally unique, remove tenant_id from this constraint: UNIQUE (email)
);

-- Create Roles Table
-- Defines roles that can be assigned to users. Roles are also tenant-specific.
CREATE TABLE IF NOT EXISTS roles (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL, -- Roles are typically tenant-specific
    name VARCHAR(100) NOT NULL, -- e.g., 'Administrator', 'Viewer', 'Editor'
    description TEXT,
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT fk_tenant
        FOREIGN KEY(tenant_id)
        REFERENCES tenants(id)
        ON DELETE CASCADE,

    UNIQUE (tenant_id, name) -- Role names must be unique within a tenant
);

-- Create Permissions Table
-- Defines granular permissions that can be associated with roles.
-- Permissions are typically pre-defined by the platform but could be extensible.
CREATE TABLE IF NOT EXISTS permissions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name VARCHAR(255) NOT NULL UNIQUE, -- e.g., 'create_vm', 'delete_storage', 'view_billing'
    description TEXT,
    resource_scope VARCHAR(100) NOT NULL, -- e.g., 'compute', 'storage', 'billing', 'all'
    action VARCHAR(100) NOT NULL,        -- e.g., 'create', 'read', 'update', 'delete', 'list'
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
    -- Permissions are generally global, roles link them to tenants.
    -- Alternatively, permissions can also be tenant_id specific if custom permissions are allowed.
    -- For simplicity in Phase 1, making them global.
);

-- Create Role_Permissions Junction Table
-- Maps roles to permissions (Many-to-Many relationship).
CREATE TABLE IF NOT EXISTS role_permissions (
    role_id UUID NOT NULL,
    permission_id UUID NOT NULL,
    assigned_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,

    PRIMARY KEY (role_id, permission_id), -- Composite primary key

    CONSTRAINT fk_role
        FOREIGN KEY(role_id)
        REFERENCES roles(id)
        ON DELETE CASCADE,

    CONSTRAINT fk_permission
        FOREIGN KEY(permission_id)
        REFERENCES permissions(id)
        ON DELETE CASCADE
);

-- Create User_Roles Junction Table
-- Maps users to roles (Many-to-Many relationship, though often a user has one primary role per tenant).
CREATE TABLE IF NOT EXISTS user_roles (
    user_id UUID NOT NULL,
    role_id UUID NOT NULL,
    assigned_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,

    PRIMARY KEY (user_id, role_id),

    CONSTRAINT fk_user
        FOREIGN KEY(user_id)
        REFERENCES users(id)
        ON DELETE CASCADE,

    CONSTRAINT fk_role
        FOREIGN KEY(role_id)
        REFERENCES roles(id)
        ON DELETE CASCADE
);

-- Indexes for performance
CREATE INDEX IF NOT EXISTS idx_users_tenant_id ON users(tenant_id);
CREATE INDEX IF NOT EXISTS idx_users_email ON users(email);
CREATE INDEX IF NOT EXISTS idx_roles_tenant_id ON roles(tenant_id);
CREATE INDEX IF NOT EXISTS idx_permissions_name ON permissions(name);

-- Trigger function to update 'updated_at' columns automatically
CREATE OR REPLACE FUNCTION trigger_set_timestamp()
RETURNS TRIGGER AS $$
BEGIN
  NEW.updated_at = NOW();
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Apply the trigger to tables with 'updated_at'
CREATE TRIGGER set_timestamp_tenants
BEFORE UPDATE ON tenants
FOR EACH ROW
EXECUTE FUNCTION trigger_set_timestamp();

CREATE TRIGGER set_timestamp_users
BEFORE UPDATE ON users
FOR EACH ROW
EXECUTE FUNCTION trigger_set_timestamp();

CREATE TRIGGER set_timestamp_roles
BEFORE UPDATE ON roles
FOR EACH ROW
EXECUTE FUNCTION trigger_set_timestamp();

-- Note on "Shared Database, Separate Schemas" for Phase 1:
-- The above DDL creates tables in the default schema (likely 'public').
-- To implement "Separate Schemas" for tenant data isolation:
-- 1. When a new tenant is created (INSERT into `tenants` table):
--    - A new schema would be dynamically created, e.g., `CREATE SCHEMA tenant_<tenant_id_or_name>;`
--    - The `tenants.schema_name` field would store this schema name.
--    - Tables containing tenant-specific data (e.g., `virtual_machines`, `databases`, etc., not defined in Phase 1)
--      would be created within this new schema: `CREATE TABLE tenant_<tenant_id>.virtual_machines (...)`.
--    - The application logic (API Gateway, workers) would need to set the `search_path`
--      or qualify table names appropriately based on the authenticated tenant context.
-- For Phase 1, the foundational tables (`tenants`, `users`, `roles`, `permissions`) are central.
-- The `tenant_id` foreign key in `users` and `roles` provides logical data separation within these shared tables.
-- True schema-per-tenant would apply to resources managed BY tenants, not these core entities themselves,
-- or these core entities could also be in tenant schemas if users/roles are fully siloed per tenant.
-- The current model uses `tenant_id` for logical separation in shared core tables.

COMMIT;
-- End of init.sql
-- Ensure the PostgreSQL service in docker-compose.yml is configured to run this script on initialization.
-- The volume mount should be: ./iac/init.sql:/docker-entrypoint-initdb.d/init.sql
-- This ensures the script is executed when the PostgreSQL container starts for the first time and the database is initialized.

-- Add a comment about how to connect and verify
-- To connect to this PostgreSQL instance from your host machine (e.g., using psql or a GUI tool):
-- Host: localhost
-- Port: 5432
-- User: admin
-- Password: password (as defined in docker-compose.yml)
-- Database: aicmp_db
--
-- You can then run SQL queries like:
-- \c aicmp_db
-- \dt -- lists tables in the current schema (public by default)
-- SELECT * FROM tenants;
-- SELECT * FROM users;
--
-- To list schemas: \dn
-- To set search path: SET search_path TO my_tenant_schema, public;
--
-- This script will be executed by the postgres container on startup if the database is empty.
-- If you modify this script after the database has been initialized, you'll need to
-- either drop the database volume (docker-compose down -v) and restart,
-- or apply the changes manually using a migration tool or psql.
-- For iterative development, using a migration tool (like Alembic, which is in requirements)
-- is recommended for schema changes after initial setup.
-- Phase 1 focuses on initial setup. Migration tooling can be integrated later.

-- Granting usage on schemas to roles is part of tenant provisioning.
-- Example (would be done programmatically when a tenant schema is created):
-- GRANT USAGE ON SCHEMA tenant_specific_schema TO tenant_user_role;
-- GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA tenant_specific_schema TO tenant_user_role;
-- ALTER DEFAULT PRIVILEGES IN SCHEMA tenant_specific_schema GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO tenant_user_role;

-- For now, all tables are in 'public' schema.
-- The application would connect as 'admin' user and use tenant_id for data filtering.
-- More refined permission model at DB level would be needed for schema-per-tenant.
-- e.g., creating a DB role per tenant that only has access to its own schema.
-- The 'admin' user defined in docker-compose is a superuser for the DB.
-- Application services should ideally use more restricted DB users.
-- This will be refined in later phases.
-- For Phase 1, the current setup with `init.sql` creating tables in the default schema is sufficient.
