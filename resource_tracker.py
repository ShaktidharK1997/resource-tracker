#!/usr/bin/env python3

import logging
import openstack
import chi
import psycopg2
from psycopg2.extras import Json
from datetime import datetime
from typing import Dict, List, Any
from keystoneauth1.identity import v3
from keystoneauth1 import session
from openstack import connection
from dotenv import load_dotenv
import os 

# Load environment variables from .env file
load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('resource_tracker.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

class ResourceTracker:
    def __init__(self, db_params: Dict[str, str], openstack_auth: Dict[str, str], blazar_auth: Dict[str, str]):
        self.db_params = db_params
        
        # Initialize OpenStack connection
        auth = v3.ApplicationCredential(
            auth_url=openstack_auth['auth_url'],
            application_credential_id=openstack_auth['application_credential_id'],
            application_credential_secret=openstack_auth['application_credential_secret']
        )
        self.os_sess = session.Session(auth=auth)
        self.os_conn = connection.Connection(session=self.os_sess)

        # Initialize Blazar connection
        blazar_auth = v3.ApplicationCredential(
            auth_url=blazar_auth['auth_url'],
            application_credential_id=blazar_auth['application_credential_id'],
            application_credential_secret=blazar_auth['application_credential_secret']
        )
        self.blazar_sess = session.Session(auth=blazar_auth)
        self.blazar_conn = chi.blazar(session=self.blazar_sess)

    def get_db_connection(self):
        """Create and return a database connection"""
        return psycopg2.connect(**self.db_params)

    def fetch_current_resources(self) -> Dict[str, List[Any]]:
        """Fetch all current resources from OpenStack and Blazar"""
        try:
            resources = {
                'servers': list(self.os_conn.compute.servers()),
                'networks': list(self.os_conn.network.networks()),
                'routers': list(self.os_conn.network.routers()),
                'subnets': list(self.os_conn.network.subnets()),
                'leases': self.blazar_conn.lease.list()
            }
            return resources
        except Exception as e:
            logger.error(f"Error fetching resources: {str(e)}")
            raise

    def update_servers(self, conn, servers: List[Any], current_time: datetime):
        """Update server records in the database"""
        try:
            with conn.cursor() as cur:
                # Get existing server IDs
                cur.execute("SELECT resource_id FROM servers")
                existing_ids = {row[0] for row in cur.fetchall()}
                
                # Process each server
                current_ids = set()
                for server in servers:
                    current_ids.add(server.id)
                    
                    # Prepare server data
                    server_data = {
                        'resource_id': server.id,
                        'resource_name': server.name,
                        'status': server.status,
                        'created_time': server.created_at,
                        'updated_time': server.updated_at,
                        'last_seen_time': current_time,
                        'flavor': server.flavor.get('id') if server.flavor else None,
                        'image': server.image.get('id') if server.image else None,
                        'security_groups': [sg.get('name') for sg in server.security_groups],
                        'addresses': Json(server.addresses)
                    }
                    
                    if server.id in existing_ids:
                        # Update existing server
                        cur.execute("""
                            UPDATE servers 
                            SET resource_name = %(resource_name)s,
                                status = %(status)s,
                                updated_time = %(updated_time)s,
                                last_seen_time = %(last_seen_time)s,
                                flavor = %(flavor)s,
                                image = %(image)s,
                                security_groups = %(security_groups)s,
                                addresses = %(addresses)s
                            WHERE resource_id = %(resource_id)s
                        """, server_data)
                    else:
                        # Insert new server
                        cur.execute("""
                            INSERT INTO servers (
                                resource_id, resource_name, status, created_time, 
                                updated_time, last_seen_time, flavor, image,
                                security_groups, addresses
                            ) VALUES (
                                %(resource_id)s, %(resource_name)s, %(status)s, %(created_time)s,
                                %(updated_time)s, %(last_seen_time)s, %(flavor)s, %(image)s,
                                %(security_groups)s, %(addresses)s
                            )
                        """, server_data)
                
                # Update first_time_not_seen for servers that no longer exist
                missing_ids = existing_ids - current_ids
                if missing_ids:
                    cur.execute("""
                        UPDATE servers 
                        SET first_time_not_seen = %s
                        WHERE resource_id = ANY(%s)
                        AND first_time_not_seen IS NULL
                    """, (current_time, list(missing_ids)))
                
        except Exception as e:
            logger.error(f"Error updating servers: {str(e)}")
            raise

    def update_networks(self, conn, networks: List[Any], current_time: datetime):
        """Update network records in the database"""
        try:
            with conn.cursor() as cur:
                # Get existing network IDs
                cur.execute("SELECT resource_id FROM networks")
                existing_ids = {row[0] for row in cur.fetchall()}
                
                # Process each network
                current_ids = set()
                for network in networks:
                    current_ids.add(network.id)
                    
                    # Prepare network data
                    network_data = {
                        'resource_id': network.id,
                        'resource_name': network.name,
                        'status': network.status,
                        'created_time': network.created_at,
                        'updated_time': network.updated_at,
                        'last_seen_time': current_time,
                        'port_security_enabled': network.is_port_security_enabled
                    }
                    
                    if network.id in existing_ids:
                        # Update existing network
                        cur.execute("""
                            UPDATE networks 
                            SET resource_name = %(resource_name)s,
                                status = %(status)s,
                                updated_time = %(updated_time)s,
                                last_seen_time = %(last_seen_time)s,
                                port_security_enabled = %(port_security_enabled)s
                            WHERE resource_id = %(resource_id)s
                        """, network_data)
                    else:
                        # Insert new network
                        cur.execute("""
                            INSERT INTO networks (
                                resource_id, resource_name, status, created_time,
                                updated_time, last_seen_time, port_security_enabled
                            ) VALUES (
                                %(resource_id)s, %(resource_name)s, %(status)s, %(created_time)s,
                                %(updated_time)s, %(last_seen_time)s, %(port_security_enabled)s
                            )
                        """, network_data)
                
                # Update first_time_not_seen for networks that no longer exist
                missing_ids = existing_ids - current_ids
                if missing_ids:
                    cur.execute("""
                        UPDATE networks 
                        SET first_time_not_seen = %s
                        WHERE resource_id = ANY(%s)
                        AND first_time_not_seen IS NULL
                    """, (current_time, list(missing_ids)))
                
        except Exception as e:
            logger.error(f"Error updating networks: {str(e)}")
            raise

    def update_routers(self, conn, routers: List[Any], current_time: datetime):
        """Update router records in the database"""
        try:
            with conn.cursor() as cur:
                # Get existing router IDs
                cur.execute("SELECT resource_id FROM routers")
                existing_ids = {row[0] for row in cur.fetchall()}
                
                # Process each router
                current_ids = set()
                for router in routers:
                    current_ids.add(router.id)
                    
                    # Prepare router data
                    router_data = {
                        'resource_id': router.id,
                        'resource_name': router.name,
                        'status': router.status,
                        'created_time': router.created_at,
                        'updated_time': router.updated_at,
                        'last_seen_time': current_time,
                        'external_gateway_info': Json(router.external_gateway_info)
                    }
                    
                    if router.id in existing_ids:
                        # Update existing router
                        cur.execute("""
                            UPDATE routers 
                            SET resource_name = %(resource_name)s,
                                status = %(status)s,
                                updated_time = %(updated_time)s,
                                last_seen_time = %(last_seen_time)s,
                                external_gateway_info = %(external_gateway_info)s
                            WHERE resource_id = %(resource_id)s
                        """, router_data)
                    else:
                        # Insert new router
                        cur.execute("""
                            INSERT INTO routers (
                                resource_id, resource_name, status, created_time,
                                updated_time, last_seen_time, external_gateway_info
                            ) VALUES (
                                %(resource_id)s, %(resource_name)s, %(status)s, %(created_time)s,
                                %(updated_time)s, %(last_seen_time)s, %(external_gateway_info)s
                            )
                        """, router_data)
                
                # Update first_time_not_seen for routers that no longer exist
                missing_ids = existing_ids - current_ids
                if missing_ids:
                    cur.execute("""
                        UPDATE routers 
                        SET first_time_not_seen = %s
                        WHERE resource_id = ANY(%s)
                        AND first_time_not_seen IS NULL
                    """, (current_time, list(missing_ids)))
                
        except Exception as e:
            logger.error(f"Error updating routers: {str(e)}")
            raise

    def update_subnets(self, conn, subnets: List[Any], current_time: datetime):
        """Update subnet records in the database"""
        try:
            with conn.cursor() as cur:
                # Get existing subnet IDs
                cur.execute("SELECT resource_id FROM subnets")
                existing_ids = {row[0] for row in cur.fetchall()}
                
                # Process each subnet
                current_ids = set()
                for subnet in subnets:
                    current_ids.add(subnet.id)
                    
                    # Prepare subnet data
                    subnet_data = {
                        'resource_id': subnet.id,
                        'resource_name': subnet.name,
                        'status': 'ACTIVE',  # Subnets don't typically have a status field
                        'created_time': subnet.created_at,
                        'updated_time': subnet.updated_at,
                        'last_seen_time': current_time,
                        'network_id': subnet.network_id,
                        'allocation_pools': Json(subnet.allocation_pools),
                        'cidr': subnet.cidr
                    }
                    
                    if subnet.id in existing_ids:
                        # Update existing subnet
                        cur.execute("""
                            UPDATE subnets 
                            SET resource_name = %(resource_name)s,
                                status = %(status)s,
                                updated_time = %(updated_time)s,
                                last_seen_time = %(last_seen_time)s,
                                network_id = %(network_id)s,
                                allocation_pools = %(allocation_pools)s,
                                cidr = %(cidr)s
                            WHERE resource_id = %(resource_id)s
                        """, subnet_data)
                    else:
                        # Insert new subnet
                        cur.execute("""
                            INSERT INTO subnets (
                                resource_id, resource_name, status, created_time,
                                updated_time, last_seen_time, network_id,
                                allocation_pools, cidr
                            ) VALUES (
                                %(resource_id)s, %(resource_name)s, %(status)s, %(created_time)s,
                                %(updated_time)s, %(last_seen_time)s, %(network_id)s,
                                %(allocation_pools)s, %(cidr)s
                            )
                        """, subnet_data)
                
                # Update first_time_not_seen for subnets that no longer exist
                missing_ids = existing_ids - current_ids
                if missing_ids:
                    cur.execute("""
                        UPDATE subnets 
                        SET first_time_not_seen = %s
                        WHERE resource_id = ANY(%s)
                        AND first_time_not_seen IS NULL
                    """, (current_time, list(missing_ids)))
                
        except Exception as e:
            logger.error(f"Error updating subnets: {str(e)}")
            raise

    def update_gpu_leases(self, conn, leases: List[Any], current_time: datetime):
        """Update GPU lease records in the database"""
        try:
            with conn.cursor() as cur:
                # Get existing lease IDs
                cur.execute("SELECT lease_id FROM gpu_leases")
                existing_ids = {row[0] for row in cur.fetchall()}
                
                # Process each lease
                current_ids = set()
                for lease in leases:
                    current_ids.add(lease['id'])
                    
                    # Prepare lease data
                    lease_data = {
                        'lease_id': lease['id'],
                        'lease_name': lease['name'],
                        'user_id': lease['user_id'],
                        'project_id': lease['project_id'],
                        'start_date': lease['start_date'],
                        'end_date': lease['end_date'],
                        'status': lease['status'],
                        'created_time': lease['created_at'],
                        'updated_time': lease['updated_at'],
                        'degraded': lease.get('degraded', False),
                        'trust_id': lease.get('trust_id'),
                        'last_seen_time': current_time
                    }
                    
                    if lease['id'] in existing_ids:
                        # Update existing lease
                        cur.execute("""
                            UPDATE gpu_leases 
                            SET lease_name = %(lease_name)s,
                                status = %(status)s,
                                start_date = %(start_date)s,
                                end_date = %(end_date)s,
                                updated_time = %(updated_time)s,
                                last_seen_time = %(last_seen_time)s,
                                degraded = %(degraded)s,
                                trust_id = %(trust_id)s
                            WHERE lease_id = %(lease_id)s
                        """, lease_data)
                    else:
                        # Insert new lease
                        cur.execute("""
                            INSERT INTO gpu_leases (
                                lease_id, lease_name, user_id, project_id,
                                start_date, end_date, status, created_time,
                                updated_time, degraded, trust_id, last_seen_time
                            ) VALUES (
                                %(lease_id)s, %(lease_name)s, %(user_id)s, %(project_id)s,
                                %(start_date)s, %(end_date)s, %(status)s, %(created_time)s,
                                %(updated_time)s, %(degraded)s, %(trust_id)s, %(last_seen_time)s
                            )
                        """, lease_data)

                    # Process reservations for this lease
                    self.update_gpu_lease_reservations(cur, lease['id'], lease['reservations'], current_time)
                
                # Update first_time_not_seen for leases that no longer exist
                missing_ids = existing_ids - current_ids
                if missing_ids:
                    cur.execute("""
                        UPDATE gpu_leases 
                        SET first_time_not_seen = %s
                        WHERE lease_id = ANY(%s)
                        AND first_time_not_seen IS NULL
                    """, (current_time, list(missing_ids)))
                
        except Exception as e:
            logger.error(f"Error updating GPU leases: {str(e)}")
            raise

    def update_gpu_lease_reservations(self, cur, lease_id: str, reservations: List[Any], current_time: datetime):
        """Update GPU lease reservation records in the database"""
        try:
            # Get existing reservation IDs for this lease
            cur.execute("SELECT reservation_id FROM gpu_lease_reservations WHERE lease_id = %s", (lease_id,))
            existing_ids = {row[0] for row in cur.fetchall()}
            
            # Process each reservation
            current_ids = set()
            for reservation in reservations:
                current_ids.add(reservation['id'])
                
                # Prepare reservation data
                reservation_data = {
                    'reservation_id': reservation['id'],
                    'lease_id': lease_id,
                    'resource_id': reservation['resource_id'],
                    'resource_type': reservation['resource_type'],
                    'status': reservation['status'],
                    'created_time': reservation['created_at'],
                    'updated_time': reservation['updated_at'],
                    'missing_resources': reservation.get('missing_resources', False),
                    'resources_changed': reservation.get('resources_changed', False),
                    'resource_properties': Json(reservation.get('resource_properties', {})),
                    'network_id': reservation.get('network_id'),
                    'min_hosts': reservation.get('min', 1),
                    'max_hosts': reservation.get('max', 1)
                }
                
                if reservation['id'] in existing_ids:
                    # Update existing reservation
                    cur.execute("""
                        UPDATE gpu_lease_reservations 
                        SET status = %(status)s,
                            updated_time = %(updated_time)s,
                            missing_resources = %(missing_resources)s,
                            resources_changed = %(resources_changed)s,
                            resource_properties = %(resource_properties)s,
                            network_id = %(network_id)s,
                            min_hosts = %(min_hosts)s,
                            max_hosts = %(max_hosts)s
                        WHERE reservation_id = %(reservation_id)s
                    """, reservation_data)
                else:
                    # Insert new reservation
                    cur.execute("""
                        INSERT INTO gpu_lease_reservations (
                            reservation_id, lease_id, resource_id, resource_type,
                            status, created_time, updated_time, missing_resources,
                            resources_changed, resource_properties, network_id,
                            min_hosts, max_hosts
                        ) VALUES (
                            %(reservation_id)s, %(lease_id)s, %(resource_id)s, %(resource_type)s,
                            %(status)s, %(created_time)s, %(updated_time)s, %(missing_resources)s,
                            %(resources_changed)s, %(resource_properties)s, %(network_id)s,
                            %(min_hosts)s, %(max_hosts)s
                        )
                    """, reservation_data)
                
        except Exception as e:
            logger.error(f"Error updating GPU lease reservations: {str(e)}")
            raise
    
    def update_resources(self):
        """Main method to update all resources"""
        current_time = datetime.now()
        
        try:
            # Fetch all current resources
            resources = self.fetch_current_resources()
            
            # Get database connection
            conn = self.get_db_connection()
            try:
                # Start transaction
                conn.autocommit = False
                
                # Update each resource type
                self.update_servers(conn, resources['servers'], current_time)
                self.update_networks(conn, resources['networks'], current_time)
                self.update_routers(conn, resources['routers'], current_time)
                self.update_subnets(conn, resources['subnets'], current_time)
                self.update_gpu_leases(conn, resources['leases'], current_time)
                
                # Commit transaction
                conn.commit()
                logger.info("Successfully updated all resources")
                
            except Exception as e:
                conn.rollback()
                logger.error(f"Error in transaction, rolling back: {str(e)}")
                raise
            finally:
                conn.close()
                
        except Exception as e:
            logger.error(f"Failed to update resources: {str(e)}")
            raise
    
def main():
    # Database connection parameters
    db_params = {
        'dbname': os.getenv('DB_NAME'),
        'user': os.getenv('DB_USER'),
        'password': os.getenv('DB_PASSWORD'),
        'host': os.getenv('DB_HOST'),
        'port': os.getenv('DB_PORT')
    }

    # OpenStack authentication parameters
    openstack_auth = {
        'auth_url': os.getenv('OS_AUTH_URL'),
        'application_credential_id': os.getenv('OS_APPLICATION_CREDENTIAL_ID'),
        'application_credential_secret': os.getenv('OS_APPLICATION_CREDENTIAL_SECRET')
    }

    # Blazar authentication parameters
    blazar_auth = {
        'auth_url': os.getenv('BLAZAR_AUTH_URL'),
        'application_credential_id': os.getenv('BLAZAR_APPLICATION_CREDENTIAL_ID'),
        'application_credential_secret': os.getenv('BLAZAR_APPLICATION_CREDENTIAL_SECRET')
    }
    
    tracker = ResourceTracker(db_params, openstack_auth, blazar_auth)
    tracker.update_resources()

if __name__ == "__main__":
    main() 