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

