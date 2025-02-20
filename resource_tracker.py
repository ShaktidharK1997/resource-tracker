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
from tabulate import tabulate

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
    def __init__(self, db_params: Dict[str, str]):
        self.db_params = db_params
        self.os_connections = {}
        self.blazar_connections = {}
        self.initialize_connections()

    def initialize_connections(self):
        """Initialize connections for all project sites"""
        # Parse OpenStack credentials
        auth_urls = os.getenv('OS_AUTH_URL', '').split(',')
        app_cred_ids = os.getenv('OS_APPLICATION_CREDENTIAL_ID', '').split(',')
        app_cred_secrets = os.getenv('OS_APPLICATION_CREDENTIAL_SECRET', '').split(',')

        # Parse Blazar credentials
        blazar_auth_urls = os.getenv('BLAZAR_AUTH_URL', '').split(',')
        blazar_app_cred_ids = os.getenv('BLAZAR_APPLICATION_CREDENTIAL_ID', '').split(',')
        blazar_app_cred_secrets = os.getenv('BLAZAR_APPLICATION_CREDENTIAL_SECRET', '').split(',')

        # Initialize OpenStack connections
        for auth_url, cred_id, secret in zip(auth_urls, app_cred_ids, app_cred_secrets):
            auth_url = auth_url.strip()
            cred_id = cred_id.strip()
            secret = secret.strip()
            
            project_site = self.get_project_site(auth_url)
            
            auth = v3.ApplicationCredential(
                auth_url=auth_url,
                application_credential_id=cred_id,
                application_credential_secret=secret
            )
            sess = session.Session(auth=auth)
            self.os_connections[project_site] = connection.Connection(session=sess)

        # Initialize Blazar connections
        for auth_url, cred_id, secret in zip(blazar_auth_urls, blazar_app_cred_ids, blazar_app_cred_secrets):
            auth_url = auth_url.strip()
            cred_id = cred_id.strip()
            secret = secret.strip()
            
            project_site = self.get_project_site(auth_url)
            
            auth = v3.ApplicationCredential(
                auth_url=auth_url,
                application_credential_id=cred_id,
                application_credential_secret=secret
            )
            sess = session.Session(auth=auth)
            self.blazar_connections[project_site] = chi.blazar(session=sess)

    def get_db_connection(self):
        """Create and return a database connection"""
        return psycopg2.connect(**self.db_params)

    def get_project_site(self, auth_url: str) -> str:
        """Determine the project_site based on the auth_url."""
        if 'kvm.tacc.chameleoncloud.org' in auth_url:
            return 'kvm@tacc'
        elif 'chi.tacc.chameleoncloud.org' in auth_url:
            return 'chi@tacc'
        elif 'chi.uc.chameleoncloud.org' in auth_url:
            return 'chi@uc'
        else:
            raise ValueError(f"Unknown auth_url: {auth_url}")

    def fetch_current_resources(self, project_site: str) -> Dict[str, List[Any]]:
        """Fetch all current resources from OpenStack and Blazar for a specific project site"""
        try:
            os_conn = self.os_connections.get(project_site)
            blazar_conn = self.blazar_connections.get(project_site)
            
            resources = {
                'servers': list(os_conn.compute.servers()) if os_conn else [],
                'networks': list(os_conn.network.networks()) if os_conn else [],
                'routers': list(os_conn.network.routers()) if os_conn else [],
                'subnets': list(os_conn.network.subnets()) if os_conn else [],
                'floating_ips': list(os_conn.network.ips()) if os_conn else [],
                'leases': blazar_conn.lease.list() if blazar_conn else []
            }
            return resources
        except Exception as e:
            logger.error(f"Error fetching resources for {project_site}: {str(e)}")
            raise
    
    def update_floating_ips(self, conn, floating_ips: List[Any], current_time: datetime, project_site: str):
        """Update floating IP records in the database"""
        try:
            with conn.cursor() as cur:
                # Get existing floating IP IDs
                cur.execute("SELECT resource_id FROM floating_ips WHERE project_site = %s",(project_site, ))
                existing_ids = {row[0] for row in cur.fetchall()}
                
                # Process each floating IP
                current_ids = set()
                for ip in floating_ips:
                    current_ids.add(ip.id)
                    
                    # Prepare floating IP data
                    ip_data = {
                        'resource_id': ip.id,
                        'resource_name': ip.description or ip.id,  # Use description or ID as name
                        'status': ip.status,
                        'created_time': ip.created_at,
                        'updated_time': ip.updated_at,
                        'last_seen_time': current_time,
                        'description': ip.description or '',
                        'floating_ip_address': ip.floating_ip_address,
                        'fixed_ip_address': ip.fixed_ip_address or '',
                        'project_site': project_site
                    }
                    
                    if ip.id in existing_ids:
                        # Update existing floating IP
                        cur.execute("""
                            UPDATE floating_ips 
                            SET resource_name = %(resource_name)s,
                                status = %(status)s,
                                updated_time = %(updated_time)s,
                                last_seen_time = %(last_seen_time)s,
                                description = %(description)s,
                                floating_ip_address = %(floating_ip_address)s,
                                fixed_ip_address = %(fixed_ip_address)s
                            WHERE resource_id = %(resource_id)s
                        """, ip_data)
                    else:
                        # Insert new floating IP
                        cur.execute("""
                            INSERT INTO floating_ips (
                                resource_id, resource_name, status, created_time,
                                updated_time, last_seen_time, description,
                                floating_ip_address, fixed_ip_address, project_site
                            ) VALUES (
                                %(resource_id)s, %(resource_name)s, %(status)s, %(created_time)s,
                                %(updated_time)s, %(last_seen_time)s, %(description)s,
                                %(floating_ip_address)s, %(fixed_ip_address)s, %(project_site)s
                            )
                        """, ip_data)
                
                # Update first_time_not_seen for floating IPs that no longer exist
                missing_ids = existing_ids - current_ids
                if missing_ids:
                    cur.execute("""
                        UPDATE floating_ips 
                        SET first_time_not_seen = %s,
                        user_deleted = TRUE
                        WHERE resource_id = ANY(%s)
                        AND first_time_not_seen IS NULL
                    """, (current_time, list(missing_ids)))
                
        except Exception as e:
            logger.error(f"Error updating floating IPs: {str(e)}")
            raise
    
    def update_servers(self, conn, servers: List[Any], current_time: datetime, project_site: str):
        """Update server records in the database"""
        try:
            with conn.cursor() as cur:
                # Get existing server IDs
                cur.execute("SELECT resource_id FROM servers WHERE project_site = %s",(project_site, ))
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
                        'addresses': Json(server.addresses),
                        'project_site': project_site
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
                                security_groups, addresses, project_site
                            ) VALUES (
                                %(resource_id)s, %(resource_name)s, %(status)s, %(created_time)s,
                                %(updated_time)s, %(last_seen_time)s, %(flavor)s, %(image)s,
                                %(security_groups)s, %(addresses)s, %(project_site)s
                            )
                        """, server_data)
                
                # Update first_time_not_seen for servers that no longer exist
                missing_ids = existing_ids - current_ids
                if missing_ids:
                    cur.execute("""
                        UPDATE servers 
                        SET first_time_not_seen = %s,
                        user_deleted = TRUE
                        WHERE resource_id = ANY(%s)
                        AND first_time_not_seen IS NULL
                    """, (current_time, list(missing_ids)))
                
        except Exception as e:
            logger.error(f"Error updating servers: {str(e)}")
            raise

    def update_networks(self, conn, networks: List[Any], current_time: datetime, project_site):
        """Update network records in the database"""
        try:
            with conn.cursor() as cur:
                # Get existing network IDs
                cur.execute("SELECT resource_id FROM networks WHERE project_site = %s",(project_site, ))
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
                        'port_security_enabled': network.is_port_security_enabled,
                        'project_site': project_site
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
                                updated_time, last_seen_time, port_security_enabled, project_site
                            ) VALUES (
                                %(resource_id)s, %(resource_name)s, %(status)s, %(created_time)s,
                                %(updated_time)s, %(last_seen_time)s, %(port_security_enabled)s, %(project_site)s
                            )
                        """, network_data)
                
                # Update first_time_not_seen for networks that no longer exist
                missing_ids = existing_ids - current_ids
                if missing_ids:
                    cur.execute("""
                        UPDATE networks 
                        SET first_time_not_seen = %s,
                        user_deleted = TRUE
                        WHERE resource_id = ANY(%s)
                        AND first_time_not_seen IS NULL
                    """, (current_time, list(missing_ids)))
                
        except Exception as e:
            logger.error(f"Error updating networks: {str(e)}")
            raise

    def update_routers(self, conn, routers: List[Any], current_time: datetime, project_site: str ):
        """Update router records in the database"""
        try:
            with conn.cursor() as cur:
                # Get existing router IDs
                cur.execute("SELECT resource_id FROM routers WHERE project_site = %s",(project_site, ))
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
                        'external_gateway_info': Json(router.external_gateway_info),
                        'project_site':project_site
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
                                updated_time, last_seen_time, external_gateway_info, project_site
                            ) VALUES (
                                %(resource_id)s, %(resource_name)s, %(status)s, %(created_time)s,
                                %(updated_time)s, %(last_seen_time)s, %(external_gateway_info)s, %(project_site)s
                            )
                        """, router_data)
                
                # Update first_time_not_seen for routers that no longer exist
                missing_ids = existing_ids - current_ids
                if missing_ids:
                    cur.execute("""
                        UPDATE routers 
                        SET first_time_not_seen = %s,
                        user_deleted = TRUE
                        WHERE resource_id = ANY(%s)
                        AND first_time_not_seen IS NULL
                    """, (current_time, list(missing_ids)))
                
        except Exception as e:
            logger.error(f"Error updating routers: {str(e)}")
            raise

    def update_subnets(self, conn, subnets: List[Any], current_time: datetime, project_site: str):
        """Update subnet records in the database"""
        try:
            with conn.cursor() as cur:
                # Get existing subnet IDs
                cur.execute("SELECT resource_id FROM subnets WHERE project_site = %s",(project_site, ))
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
                        'cidr': subnet.cidr,
                        'project_site': project_site
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
                                allocation_pools, cidr, project_site
                            ) VALUES (
                                %(resource_id)s, %(resource_name)s, %(status)s, %(created_time)s,
                                %(updated_time)s, %(last_seen_time)s, %(network_id)s,
                                %(allocation_pools)s, %(cidr)s, %(project_site)s
                            )
                        """, subnet_data)
                
                # Update first_time_not_seen for subnets that no longer exist
                missing_ids = existing_ids - current_ids
                if missing_ids:
                    cur.execute("""
                        UPDATE subnets 
                        SET first_time_not_seen = %s,
                        user_deleted = TRUE
                        WHERE resource_id = ANY(%s)
                        AND first_time_not_seen IS NULL
                    """, (current_time, list(missing_ids)))
                
        except Exception as e:
            logger.error(f"Error updating subnets: {str(e)}")
            raise

    def update_gpu_leases(self, conn, leases: List[Any], current_time: datetime, project_site: str):
        """Update GPU lease records in the database"""
        try:
            with conn.cursor() as cur:
                # Get existing lease IDs
                cur.execute("SELECT lease_id FROM gpu_leases WHERE project_site = %s",(project_site, ))
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
                        #'trust_id': lease.get('trust_id'),
                        'last_seen_time': current_time,
                        'project_site': project_site
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
                                degraded = %(degraded)s
                            WHERE lease_id = %(lease_id)s
                        """, lease_data)
                    else:
                        # Insert new lease
                        cur.execute("""
                            INSERT INTO gpu_leases (
                                lease_id, lease_name, user_id, project_id,
                                start_date, end_date, status, created_time,
                                updated_time, degraded, last_seen_time, project_site
                            ) VALUES (
                                %(lease_id)s, %(lease_name)s, %(user_id)s, %(project_id)s,
                                %(start_date)s, %(end_date)s, %(status)s, %(created_time)s,
                                %(updated_time)s, %(degraded)s, %(last_seen_time)s, %(project_site)s
                            )
                        """, lease_data)

                    # Process reservations for this lease
                    self.update_gpu_lease_reservations(cur, lease['id'], lease['reservations'], current_time, project_site)
                
                # Update first_time_not_seen for leases that no longer exist
                missing_ids = existing_ids - current_ids
                if missing_ids:
                    cur.execute("""
                        UPDATE gpu_leases 
                        SET first_time_not_seen = %s,
                        user_deleted = TRUE
                        WHERE lease_id = ANY(%s)
                        AND first_time_not_seen IS NULL
                    """, (current_time, list(missing_ids)))
                
        except Exception as e:
            logger.error(f"Error updating GPU leases: {str(e)}")
            raise

    def update_gpu_lease_reservations(self, cur, lease_id: str, reservations: List[Any], current_time: datetime, project_site: str):
        """Update GPU lease reservation records in the database"""
        try:
            # Get existing reservation IDs for this lease
            cur.execute("SELECT reservation_id FROM gpu_lease_reservations WHERE lease_id = %s and project_site = %s", (lease_id,project_site, ))
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
                    'project_site': project_site
                    #'min_hosts': reservation.get('min', 1),
                    #'max_hosts': reservation.get('max', 1)
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
                            network_id = %(network_id)s
                        WHERE reservation_id = %(reservation_id)s
                    """, reservation_data)
                else:
                    # Insert new reservation
                    cur.execute("""
                        INSERT INTO gpu_lease_reservations (
                            reservation_id, lease_id, resource_id, resource_type,
                            status, created_time, updated_time, missing_resources,
                            resources_changed, resource_properties, network_id, project_site
                        ) VALUES (
                            %(reservation_id)s, %(lease_id)s, %(resource_id)s, %(resource_type)s,
                            %(status)s, %(created_time)s, %(updated_time)s, %(missing_resources)s,
                            %(resources_changed)s, %(resource_properties)s, %(network_id)s, %(project_site)s
                        )
                    """, reservation_data)
                
        except Exception as e:
            logger.error(f"Error updating GPU lease reservations: {str(e)}")
            raise
    
    def update_resources(self):
        """Main method to update all resources across all project sites"""
        current_time = datetime.now()
        
        try:
            conn = self.get_db_connection()
            conn.autocommit = False
            
            try:
                # Update resources for each project site
                for project_site in self.os_connections.keys():
                    logger.info(f"Updating resources for project site: {project_site}")
                    resources = self.fetch_current_resources(project_site)
                    
                    # Update each resource type with project_site
                    self.update_servers(conn, resources['servers'], current_time, project_site)
                    self.update_networks(conn, resources['networks'], current_time, project_site)
                    self.update_routers(conn, resources['routers'], current_time, project_site)
                    self.update_subnets(conn, resources['subnets'], current_time, project_site)
                    self.update_floating_ips(conn, resources['floating_ips'], current_time, project_site)
                    
                    # Update Blazar leases if available for this site
                    if project_site in self.blazar_connections:
                        self.update_gpu_leases(conn, resources['leases'], current_time, project_site)
                
                conn.commit()
                logger.info("Successfully updated all resources across all project sites")
                
            except Exception as e:
                conn.rollback()
                logger.error(f"Error in transaction, rolling back: {str(e)}")
                raise
            finally:
                conn.close()
                
        except Exception as e:
            logger.error(f"Failed to update resources: {str(e)}")
            raise


    def display_resources(self, resources: Dict[str, List[Dict]]):
        """Display given resources using tabulate"""
        for resource_type, items in resources.items():
            if items:
                print(f"\n{resource_type.upper()} that have the query string in them:")
                table_data = []
                for item in items:
                    row = [
                        item['resource_id'],
                        item['resource_name'],
                        item['created_time'].strftime('%Y-%m-%d %H:%M:%S'),
                        item['last_seen_time'].strftime('%Y-%m-%d %H:%M:%S'),
                        item['project_site']
                    ]
                    table_data.append(row)

                headers = ['ID', 'Name', 'Created Time', 'Last Seen Time', 'Project Site']
                print(tabulate(table_data, headers=headers, tablefmt='grid'))
    
def main():
    # Database connection parameters
    db_params = {
        'dbname': os.getenv('DB_NAME'),
        'user': os.getenv('DB_USER'),
        'password': os.getenv('DB_PASSWORD'),
        'host': os.getenv('DB_HOST'),
        'port': os.getenv('DB_PORT')
    }
    
    tracker = ResourceTracker(db_params)
    tracker.update_resources()

if __name__ == "__main__":
    main()