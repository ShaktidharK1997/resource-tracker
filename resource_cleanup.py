#!/usr/bin/env python3

import argparse
import logging
import os
import sys
from datetime import datetime, timedelta
import openstack
import psycopg2
from psycopg2.extras import RealDictCursor
from typing import Dict, List, Any
from dotenv import load_dotenv
from keystoneauth1.identity import v3
from keystoneauth1 import session
from openstack import connection
from tabulate import tabulate

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('resource_cleanup.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

class ResourceCleaner:
    def __init__(self):

        self.db_params = {
            'dbname': os.getenv('DB_NAME'),
            'user': os.getenv('DB_USER'),
            'password': os.getenv('DB_PASSWORD'),
            'host': os.getenv('DB_HOST'),
            'port': os.getenv('DB_PORT')
        }


        auth = v3.ApplicationCredential(
            auth_url=os.getenv('OS_AUTH_URL'),
            application_credential_id=os.getenv('OS_APPLICATION_CREDENTIAL_ID'),
            application_credential_secret=os.getenv('OS_APPLICATION_CREDENTIAL_SECRET')
        )
        self.os_sess = session.Session(auth=auth)
        self.os_conn = connection.Connection(session=self.os_sess)

        self.protected_resources = {
            'networks': ['public', 'sharednet1'],
            'subnets': ['sharednet1-subnet']
        }

    def get_resources_to_delete(self, hours: int) -> Dict[str, List[Dict]]:
        """Get resources older than specified hours that are still active"""

        # Calculating cut off time as (current timestamp - no of hours given as argument)
        cutoff_time = datetime.now() - timedelta(hours=hours)
        
        try:
            with psycopg2.connect(**self.db_params) as conn:
                with conn.cursor(cursor_factory=RealDictCursor) as cur:
                    resources = {}
                    
                    # Servers query
                    cur.execute("""
                        SELECT 
                            resource_id, resource_name, status, created_time,
                            updated_time, last_seen_time, first_time_not_seen,
                            flavor, image, security_groups, addresses
                        FROM servers
                        WHERE created_time < %s
                        AND first_time_not_seen IS NULL
                        ORDER BY created_time ASC
                    """, (cutoff_time,))
                    resources['servers'] = cur.fetchall()
                    
                    # Networks query
                    cur.execute("""
                        SELECT 
                            resource_id, resource_name, status, created_time,
                            updated_time, last_seen_time, first_time_not_seen,
                            port_security_enabled
                        FROM networks
                        WHERE created_time < %s
                        AND first_time_not_seen IS NULL
                        AND resource_name NOT IN %s
                        ORDER BY created_time ASC
                    """, (cutoff_time, tuple(self.protected_resources['networks'])))
                    resources['networks'] = cur.fetchall()
                    
                    # Routers query
                    cur.execute("""
                        SELECT 
                            resource_id, resource_name, status, created_time,
                            updated_time, last_seen_time, first_time_not_seen,
                            external_gateway_info
                        FROM routers
                        WHERE created_time < %s
                        AND first_time_not_seen IS NULL
                        ORDER BY created_time ASC
                    """, (cutoff_time,))
                    resources['routers'] = cur.fetchall()
                    
                    # Subnets query
                    cur.execute("""
                        SELECT 
                            resource_id, resource_name, status, created_time,
                            updated_time, last_seen_time, first_time_not_seen,
                            network_id, allocation_pools, cidr
                        FROM subnets
                        WHERE created_time < %s
                        AND first_time_not_seen IS NULL
                        AND resource_name NOT IN %s
                        ORDER BY created_time ASC
                    """, (cutoff_time, tuple(self.protected_resources['subnets'])))
                    resources['subnets'] = cur.fetchall()
                        
            return resources
            
        except Exception as e:
            logger.error(f"Database error: {str(e)}")
            raise

    def display_resources(self, resources: Dict[str, List[Dict]]):
        """Display resources that will be deleted"""
        for resource_type, items in resources.items():
            if items:
                print(f"\n{resource_type.upper()} to be deleted:")
                table_data = []
                for item in items:
                    age = datetime.now() - item['created_time']
                    row = [
                        item['resource_name'],
                        item['status'],
                        item['created_time'].strftime('%Y-%m-%d %H:%M:%S'),
                        f"{age.days}d {age.seconds//3600}h",
                        item['last_seen_time'].strftime('%Y-%m-%d %H:%M:%S')
                    ]
                    
                    # Add resource-specific information
                    if resource_type == 'servers':
                        row.append(f"Flavor: {item['flavor']}")
                    elif resource_type == 'subnets':
                        row.append(f"CIDR: {item['cidr']}")
                    
                    table_data.append(row)

                headers = ['Name', 'Status', 'Created', 'Age', 'Last Seen', 'Details']
                print(tabulate(table_data, headers=headers, tablefmt='grid'))


    def release_floating_ips(self, server_data: Dict, dry_run: bool = True):
        """Release floating IPs associated with a server"""
        if not server_data.get('addresses'):
            return

        for network_name, addresses in server_data['addresses'].items():
            for addr in addresses:
                if addr.get('OS-EXT-IPS:type') == 'floating':
                    ip_address = addr.get('addr')
                    if ip_address:
                        if dry_run:
                            logger.info(f"Would release floating IP: {ip_address}")
                        else:
                            try:
                                floating_ips = list(self.os_conn.network.ips())
                                for ip in floating_ips:
                                    if ip.floating_ip_address == ip_address:
                                        self.os_conn.network.delete_ip(ip.id)
                                        logger.info(f"Released floating IP: {ip_address}")
                                        break
                            except Exception as e:
                                logger.error(f"Error releasing floating IP {ip_address}: {str(e)}")

    def clean_router(self, router_data: Dict, dry_run: bool = True):
        """Clean router by removing external gateway and interfaces"""
        try:
            router_id = router_data['resource_id']
            if dry_run:
                if router_data.get('external_gateway_info'):
                    logger.info(f"Would remove external gateway from router: {router_id}")
                logger.info(f"Would remove interfaces from router: {router_id}")
                return

            # Get router ports
            ports = self.os_conn.network.ports(device_id=router_id)
            
            # Remove external gateway if exists
            if router_data.get('external_gateway_info'):
                self.os_conn.network.update_router(router_id, external_gateway_info={})
                logger.info(f"Removed external gateway from router: {router_id}")

            # Remove router interfaces
            for port in ports:
                if port.device_owner == 'network:router_interface':
                    self.os_conn.network.remove_interface_from_router(
                        router_id,
                        subnet_id=port.fixed_ips[0]['subnet_id']
                    )
            logger.info(f"Removed interfaces from router: {router_id}")

        except Exception as e:
            logger.error(f"Error cleaning router {router_id}: {str(e)}")
            raise

    def delete_resources(self, resources: Dict[str, List[Dict]], dry_run: bool = True):
        """Delete the specified resources in the correct order"""
        if dry_run:
            logger.info("DRY RUN - No resources will be deleted")
            self.display_resources(resources)
            return

        # Track successfully deleted resources
        deleted_resources = {
            'servers': [],
            'routers': [],
            'subnets': [],
            'networks': []
        }

        try:
            # 1. Delete servers first
            for server in resources['servers']:
                try:
                    server_id = server['resource_id']
                    logger.info(f"Deleting server: {server['resource_name']} ({server['status']})")
                    
                    # Release floating IPs first
                    self.release_floating_ips(server, dry_run=False)
                    
                    # Delete the server
                    self.os_conn.compute.delete_server(server_id)
                    deleted_resources['servers'].append(server_id)
                    logger.info(f"Deleted server: {server_id}")
                except Exception as e:
                    logger.error(f"Error deleting server {server_id}: {str(e)}")
                    continue

            # 2. Clean and delete routers
            for router in resources['routers']:
                try:
                    router_id = router['resource_id']
                    logger.info(f"Processing router: {router['resource_name']} ({router['status']})")
                    
                    # Clean router first
                    self.clean_router(router, dry_run=False)
                    
                    # Delete the router
                    self.os_conn.network.delete_router(router_id)
                    deleted_resources['routers'].append(router_id)
                    logger.info(f"Deleted router: {router_id}")
                except Exception as e:
                    logger.error(f"Error deleting router {router_id}: {str(e)}")
                    continue

            # 3. Delete subnets
            for subnet in resources['subnets']:
                try:
                    subnet_id = subnet['resource_id']
                    logger.info(f"Deleting subnet: {subnet['resource_name']} ({subnet['cidr']})")
                    self.os_conn.network.delete_subnet(subnet_id)
                    deleted_resources['subnets'].append(subnet_id)
                    logger.info(f"Deleted subnet: {subnet_id}")
                except Exception as e:
                    logger.error(f"Error deleting subnet {subnet_id}: {str(e)}")
                    continue

            # 4. Finally delete networks
            for network in resources['networks']:
                try:
                    network_id = network['resource_id']
                    logger.info(f"Deleting network: {network['resource_name']} ({network['status']})")
                    self.os_conn.network.delete_network(network_id)
                    deleted_resources['networks'].append(network_id)
                    logger.info(f"Deleted network: {network_id}")
                except Exception as e:
                    logger.error(f"Error deleting network {network_id}: {str(e)}")
                    continue

            # Bulk update all successfully deleted resources
            with psycopg2.connect(**self.db_params) as conn:
                with conn.cursor() as cur:
                    for resource_type, resource_ids in deleted_resources.items():
                        if resource_ids:  # Only update if we have deleted resources
                            cur.execute(f"""
                                UPDATE {resource_type}
                                SET system_deleted = TRUE,
                                    updated_time = NOW()
                                WHERE resource_id = ANY(%s)
                            """, (resource_ids,))
                            logger.info(f"Updated {len(resource_ids)} {resource_type} as system_deleted")
                    conn.commit()

        except Exception as e:
            logger.error(f"Error during resource deletion: {str(e)}")
            raise


def main():
    parser = argparse.ArgumentParser(description='Clean up old OpenStack and Blazar resources')
    parser.add_argument('hours', type=int, help='Delete resources older than this many hours')
    parser.add_argument('--dry-run', action='store_true', help='Show what would be deleted without actually deleting')
    args = parser.parse_args()

    if args.hours < 1:
        logger.error("Hours must be a positive integer")
        sys.exit(1)

    try:
        cleaner = ResourceCleaner()
        resources = cleaner.get_resources_to_delete(args.hours)
        cleaner.delete_resources(resources, dry_run=args.dry_run)
        
    except Exception as e:
        logger.error(f"Cleanup failed: {str(e)}")
        sys.exit(1)

if __name__ == "__main__":
    main()