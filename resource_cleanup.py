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

    def get_resources_to_delete(self, hours: int, resource_type: List[str]) -> Dict[str, List[Dict]]:
        """Get resources older than specified hours that are still active"""

        # Calculating cut off time as (current timestamp - no of hours given as argument)
        cutoff_time = datetime.now() - timedelta(hours=hours)
        
        try:
            with psycopg2.connect(**self.db_params) as conn:
                with conn.cursor(cursor_factory=RealDictCursor) as cur:
                    resources = {}
                    
                    # Servers query
                    if 'servers' in resource_type:
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
                    if 'networks' in resource_type:
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
                    if 'routers' in resource_type:
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
                    if 'subnets' in resource_type:
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
                    
                    # Floating IPs query
                    if 'floating_ips' in resource_type:
                        cur.execute("""
                            SELECT 
                                resource_id, resource_name, status, created_time,
                                updated_time, last_seen_time, first_time_not_seen,
                                description, floating_ip_address, fixed_ip_address
                            FROM floating_ips
                            WHERE created_time < %s
                            AND first_time_not_seen IS NULL
                            ORDER BY created_time ASC
                        """, (cutoff_time,))
                        resources['floating_ips'] = cur.fetchall()
                        
            return resources
            
        except Exception as e:
            logger.error(f"Database error: {str(e)}")
            raise

    def display_resources(self, resources: Dict[str, List[Dict]]):
        """Display given resources using tabulate"""
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
                    elif resource_type == 'floating_ips':
                        row.append(f"Description: {item['description']}")
                    
                    table_data.append(row)

                headers = ['Name', 'Status', 'Created', 'Age', 'Last Seen', 'Details']
                print(tabulate(table_data, headers=headers, tablefmt='grid'))

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
            'networks': [],
            'floating_ips': []
        }

        try:
            # 1. Delete servers first
            if 'servers' in resources:
                for server in resources['servers']:
                    try:
                        server_id = server['resource_id']
                        logger.info(f"Deleting server: {server['resource_name']} ({server['status']})")
                        self.os_conn.compute.delete_server(server_id)
                        deleted_resources['servers'].append(server_id)
                        logger.info(f"Deleted server: {server_id}")
                    except Exception as e:
                        logger.error(f"Error deleting server {server_id}: {str(e)}")
                        continue

            # 2. Delete Ports on the networks
            if 'networks' in resources:
                for network in resources['networks']:
                    try:
                        network_id = network['resource_id']
                        logger.info(f"Deleting port on network: {network['resource_name']}")
                        ports = self.os_conn.network.ports(network_id=network_id)
                        for port in ports:
                            self.os_conn.network.delete_port(port=port.id, ignore_missing=False)
                            logger.info(f"Deleted port {port.id} on network : {network_id}")
                    except Exception as e:
                        logger.error(f"Error deleting port {port.id} on network {network_id}: {str(e)}")
                        continue

            # 3. Delete subnets
            if 'subnets' in resources:
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

            # 4. Delete networks
            if 'networks' in resources:
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

            # 5. Delete Floating IPs
            if 'floating_ips' in resources:
                for ip in resources['floating_ips']:
                    try:
                        ip_id = ip['resource_id']
                        logger.info(f"Deleting floating ip: {ip['resource_name']}")
                        self.os_conn.network.delete_ip(ip_id)
                        deleted_resources['floating_ips'].append(ip_id)
                        logger.info(f"Deleted floating ip: {ip['resource_name']}")
                    except Exception as e:
                        logger.error(f"Error deleting floating ip {ip_id}: {str(e)}")
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
    parser.add_argument('--resource-type', nargs='+', choices=['servers', 'networks', 'routers', 'subnets', 'floating_ips','all'], default=['all'], help='Specify resource types to delete')
    args = parser.parse_args()

    if args.hours < 1:
        logger.error("Hours must be a positive integer")
        sys.exit(1)

    try:
        cleaner = ResourceCleaner()
        if 'all' in args.resource_type:
            resource_type = ['servers', 'networks', 'routers', 'subnets', 'floating_ips']
        else:
            resource_type = args.resource_type
        resources = cleaner.get_resources_to_delete(args.hours, resource_type)
        cleaner.delete_resources(resources, dry_run=args.dry_run)
        
    except Exception as e:
        logger.error(f"Cleanup failed: {str(e)}")
        sys.exit(1)

if __name__ == "__main__":
    main()