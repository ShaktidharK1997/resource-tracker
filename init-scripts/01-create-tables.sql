-- Servers table
CREATE TABLE servers (
    resource_id VARCHAR PRIMARY KEY,
    resource_name VARCHAR NOT NULL,
    status VARCHAR NOT NULL,
    created_time TIMESTAMP NOT NULL,
    updated_time TIMESTAMP NOT NULL,
    last_seen_time TIMESTAMP NOT NULL,
    first_time_not_seen TIMESTAMP,
    flavor VARCHAR,
    image VARCHAR,
    security_groups TEXT[],
    addresses JSONB,
    user_deleted BOOLEAN NOT NULL DEFAULT FALSE,
    system_deleted BOOLEAN NOT NULL DEFAULT FALSE
);

-- Networks table
CREATE TABLE networks (
    resource_id VARCHAR PRIMARY KEY,
    resource_name VARCHAR NOT NULL,
    status VARCHAR NOT NULL,
    created_time TIMESTAMP NOT NULL,
    updated_time TIMESTAMP NOT NULL,
    last_seen_time TIMESTAMP NOT NULL,
    first_time_not_seen TIMESTAMP,
    port_security_enabled BOOLEAN,
    user_deleted BOOLEAN NOT NULL DEFAULT FALSE,
    system_deleted BOOLEAN NOT NULL DEFAULT FALSE
);

-- Routers table
CREATE TABLE routers (
    resource_id VARCHAR PRIMARY KEY,
    resource_name VARCHAR NOT NULL,
    status VARCHAR NOT NULL,
    created_time TIMESTAMP NOT NULL,
    updated_time TIMESTAMP NOT NULL,
    last_seen_time TIMESTAMP NOT NULL,
    first_time_not_seen TIMESTAMP,
    external_gateway_info JSONB,
    user_deleted BOOLEAN NOT NULL DEFAULT FALSE,
    system_deleted BOOLEAN NOT NULL DEFAULT FALSE
);

-- Subnets table
CREATE TABLE subnets (
    resource_id VARCHAR PRIMARY KEY,
    resource_name VARCHAR NOT NULL,
    status VARCHAR NOT NULL,
    created_time TIMESTAMP NOT NULL,
    updated_time TIMESTAMP NOT NULL,
    last_seen_time TIMESTAMP NOT NULL,
    first_time_not_seen TIMESTAMP,
    network_id VARCHAR,
    allocation_pools JSONB,
    cidr VARCHAR,
    user_deleted BOOLEAN NOT NULL DEFAULT FALSE,
    system_deleted BOOLEAN NOT NULL DEFAULT FALSE
);

-- GPU Leases table
CREATE TABLE gpu_leases (
    lease_id VARCHAR PRIMARY KEY,
    lease_name VARCHAR NOT NULL,
    user_id VARCHAR NOT NULL,
    project_id VARCHAR NOT NULL,
    start_date TIMESTAMP NOT NULL,
    end_date TIMESTAMP NOT NULL,
    status VARCHAR NOT NULL,
    created_time TIMESTAMP NOT NULL,
    updated_time TIMESTAMP,
    degraded BOOLEAN DEFAULT FALSE,
    last_seen_time TIMESTAMP NOT NULL,
    first_time_not_seen TIMESTAMP,
    user_deleted BOOLEAN NOT NULL DEFAULT FALSE,
    system_deleted BOOLEAN NOT NULL DEFAULT FALSE
);

-- GPU Lease Reservations table
CREATE TABLE gpu_lease_reservations (
    reservation_id VARCHAR PRIMARY KEY,
    lease_id VARCHAR REFERENCES gpu_leases(lease_id),
    resource_id VARCHAR NOT NULL,
    resource_type VARCHAR NOT NULL,
    status VARCHAR NOT NULL,
    created_time TIMESTAMP NOT NULL,
    updated_time TIMESTAMP,
    missing_resources BOOLEAN DEFAULT FALSE,
    resources_changed BOOLEAN DEFAULT FALSE,
    resource_properties JSONB,
    network_id VARCHAR
);

CREATE TABLE floating_ips (
    resource_id VARCHAR NOT NULL,
    resource_name VARCHAR NOT NULL,
    status VARCHAR NOT NULL,
    created_time TIMESTAMP NOT NULL,
    updated_time TIMESTAMP NOT NULL,
    last_seen_time TIMESTAMP NOT NULL,
    first_time_not_seen TIMESTAMP,
    description VARCHAR NOT NULL,
    floating_ip_address VARCHAR NOT NULL,
    fixed_ip_address VARCHAR NOT NULL
);