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
    addresses JSONB
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
    port_security_enabled BOOLEAN
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
    external_gateway_info JSONB
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
    cidr VARCHAR
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
    updated_time TIMESTAMP NOT NULL,
    degraded BOOLEAN DEFAULT FALSE,
    trust_id VARCHAR,
    last_seen_time TIMESTAMP NOT NULL,
    first_time_not_seen TIMESTAMP
);

-- GPU Lease Reservations table
CREATE TABLE gpu_lease_reservations (
    reservation_id VARCHAR PRIMARY KEY,
    lease_id VARCHAR REFERENCES gpu_leases(lease_id),
    resource_id VARCHAR NOT NULL,
    resource_type VARCHAR NOT NULL,
    status VARCHAR NOT NULL,
    created_time TIMESTAMP NOT NULL,
    updated_time TIMESTAMP NOT NULL,
    missing_resources BOOLEAN DEFAULT FALSE,
    resources_changed BOOLEAN DEFAULT FALSE,
    resource_properties JSONB,
    network_id VARCHAR,
    min_hosts INTEGER,
    max_hosts INTEGER
);