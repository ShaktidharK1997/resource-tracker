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

        self.os_connections = {}
        self.initialize_connections()

        self.protected_resources = {
            'networks': ['public', 'sharednet1'],
            'subnets': ['sharednet1-subnet']
        }

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
    
    def initialize_connections(self):
        """Initialize connections for all project sites"""
        # Parse OpenStack credentials
        auth_urls = os.getenv('OS_AUTH_URL', '').split(',')
        app_cred_ids = os.getenv('OS_APPLICATION_CREDENTIAL_ID', '').split(',')
        app_cred_secrets = os.getenv('OS_APPLICATION_CREDENTIAL_SECRET', '').split(',')

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
        
    def get_resources_to_delete(self, hours: int, resource_type: List[str], project_site: str = None) -> Dict[str, List[Dict]]:
        """Get resources older than specified hours that are still active"""
        cutoff_time = datetime.now() - timedelta(hours=hours)
        site_condition = "AND project_site = %s" if project_site else ""

        try:
            with psycopg2.connect(**self.db_params) as conn:
                with conn.cursor(cursor_factory=RealDictCursor) as cur:
                    resources = {}
                    
                    query_params = [cutoff_time]
                    if project_site:
                        query_params.append(project_site)
                    
                    # Servers query - this was missing before
                    if 'servers' in resource_type:
                        cur.execute(f"""
                            SELECT 
                                resource_id, resource_name, status, created_time,
                                updated_time, last_seen_time, first_time_not_seen,
                                flavor, image, security_groups, addresses, project_site
                            FROM servers
                            WHERE created_time < %s
                            AND first_time_not_seen IS NULL
                            {site_condition}
                            ORDER BY created_time ASC
                        """, query_params)
                        resources['servers'] = cur.fetchall()
                        logger.debug(f"Found {len(resources['servers'])} servers to delete")

                # Networks query
                    if 'networks' in resource_type:
                        network_params = query_params + [tuple(self.protected_resources['networks'])]
                        cur.execute(f"""
                            SELECT 
                                resource_id, resource_name, status, created_time,
                                updated_time, last_seen_time, first_time_not_seen,
                                port_security_enabled, project_site
                            FROM networks
                            WHERE created_time < %s
                            AND first_time_not_seen IS NULL
                            {site_condition}
                            AND resource_name NOT IN %s
                            ORDER BY created_time ASC
                        """, network_params)
                        resources['networks'] = cur.fetchall()
                    
                    # Subnets query
                    if 'subnets' in resource_type:
                        subnet_params = query_params + [tuple(self.protected_resources['subnets'])]
                        cur.execute(f"""
                            SELECT 
                                resource_id, resource_name, status, created_time,
                                updated_time, last_seen_time, first_time_not_seen,
                                network_id, allocation_pools, cidr, project_site
                            FROM subnets
                            WHERE created_time < %s
                            AND first_time_not_seen IS NULL
                            {site_condition}
                            AND resource_name NOT IN %s
                            ORDER BY created_time ASC
                        """, subnet_params)
                        resources['subnets'] = cur.fetchall()
                    
                    # Routers query
                    if 'routers' in resource_type:
                        cur.execute(f"""
                            SELECT 
                                resource_id, resource_name, status, created_time,
                                updated_time, last_seen_time, first_time_not_seen,
                                external_gateway_info, project_site
                            FROM routers
                            WHERE created_time < %s
                            AND first_time_not_seen IS NULL
                            {site_condition}
                            ORDER BY created_time ASC
                        """, query_params)
                        resources['routers'] = cur.fetchall()
                    
                    # Floating IPs query
                    if 'floating_ips' in resource_type:
                        cur.execute(f"""
                            SELECT 
                                resource_id, resource_name, status, created_time,
                                updated_time, last_seen_time, first_time_not_seen,
                                description, floating_ip_address, fixed_ip_address, project_site
                            FROM floating_ips
                            WHERE created_time < %s
                            AND first_time_not_seen IS NULL
                            {site_condition}
                            ORDER BY created_time ASC
                        """, query_params)
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
                        item['last_seen_time'].strftime('%Y-%m-%d %H:%M:%S'),
                        item['project_site']
                    ]
                    
                    # Add resource-specific information
                    if resource_type == 'servers':
                        row.append(f"Flavor: {item['flavor']}")
                    elif resource_type == 'subnets':
                        row.append(f"CIDR: {item['cidr']}")
                    elif resource_type == 'floating_ips':
                        row.append(f"Description: {item['description']}")
                    
                    table_data.append(row)

                headers = ['Name', 'Status', 'Created', 'Age', 'Last Seen', 'Project Site', 'Details']
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

            # Group resources by project site
            resources_by_site = {}
            for resource_type, items in resources.items():
                for item in items:
                    site = item['project_site']
                    if site not in resources_by_site:
                        resources_by_site[site] = {
                            'servers': [], 'routers': [], 'subnets': [],
                            'networks': [], 'floating_ips': []
                        }
                    resources_by_site[site][resource_type].append(item)
            
            for site, site_resources in resources_by_site.items():
                os_conn = self.os_connections.get(site)
                if not os_conn:
                    logger.error(f"No connection available for site {site}")
                    continue
            
                # 1. Delete servers first
                if site_resources['servers']:
                    for server in site_resources['servers']:
                        try:
                            server_id = server['resource_id']
                            logger.info(f"Deleting server: {server['resource_name']} ({server['status']})")
                            os_conn.compute.delete_server(server_id)
                            deleted_resources['servers'].append(server_id)
                            logger.info(f"Deleted server: {server_id}")
                        except Exception as e:
                            logger.error(f"Error deleting server {server_id}: {str(e)}")
                            continue

                # 2. Delete Ports on the networks
                if site_resources['networks']:
                    for network in site_resources['networks']:
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
                if site_resources['subnets']:
                    for subnet in site_resources['subnets']:
                        try:
                            subnet_id = subnet['resource_id']
                            logger.info(f"Deleting subnet: {subnet['resource_name']} ({subnet['cidr']})")
                            os_conn.network.delete_subnet(subnet_id)
                            deleted_resources['subnets'].append(subnet_id)
                            logger.info(f"Deleted subnet: {subnet_id}")
                        except Exception as e:
                            logger.error(f"Error deleting subnet {subnet_id}: {str(e)}")
                            continue

                # 4. Delete networks
                if site_resources['networks']:
                    for network in site_resources['networks']:
                        try:
                            network_id = network['resource_id']
                            logger.info(f"Deleting network: {network['resource_name']} ({network['status']})")
                            os_conn.network.delete_network(network_id)
                            deleted_resources['networks'].append(network_id)
                            logger.info(f"Deleted network: {network_id}")
                        except Exception as e:
                            logger.error(f"Error deleting network {network_id}: {str(e)}")
                            continue

                # 5. Delete Floating IPs
                if site_resources['floating_ips']:
                    for ip in site_resources['floating_ips']:
                        try:
                            ip_id = ip['resource_id']
                            logger.info(f"Deleting floating ip: {ip['resource_name']}")
                            os_conn.network.delete_ip(ip_id)
                            deleted_resources['floating_ips'].append(ip_id)
                            logger.info(f"Deleted floating ip: {ip['resource_name']}")
                        except Exception as e:
                            logger.error(f"Error deleting floating ip {ip_id}: {str(e)}")
                            continue

                # Bulk update all successfully deleted resources
            with psycopg2.connect(**self.db_params) as conn:
                with conn.cursor() as cur:
                    for resource_type, resource_ids in deleted_resources.items():
                        if resource_ids:
                            cur.execute(f"""
                                UPDATE {resource_type}
                                SET system_deleted = TRUE,
                                    updated_time = NOW()
                                WHERE resource_id = ANY(%s)
                            """, (resource_ids,))
                    conn.commit()

        except Exception as e:
            logger.error(f"Error during resource deletion: {str(e)}")
            raise


def main():
    parser = argparse.ArgumentParser(description='Clean up old OpenStack resources')
    parser.add_argument('hours', type=int, help='Delete resources older than this many hours')
    parser.add_argument('--dry-run', action='store_true', help='Show what would be deleted without actually deleting')
    parser.add_argument('--resource-type', nargs='+', 
                      choices=['servers', 'networks', 'routers', 'subnets', 'floating_ips', 'all'],
                      default=['all'], help='Specify resource types to delete')
    parser.add_argument('--site', choices=['kvm@tacc', 'chi@tacc', 'chi@uc'],
                      help='Optional: Filter by project site')
    args = parser.parse_args()

    if args.hours < 1:
        logger.error("Hours must be a positive integer")
        sys.exit(1)

    try:
        cleaner = ResourceCleaner()
        resource_type = ['servers', 'networks', 'routers', 'subnets', 'floating_ips'] if 'all' in args.resource_type else args.resource_type
        resources = cleaner.get_resources_to_delete(args.hours, resource_type, args.site)
        cleaner.delete_resources(resources, dry_run=args.dry_run)
        
    except Exception as e:
        logger.error(f"Cleanup failed: {str(e)}")
        sys.exit(1)

if __name__ == "__main__":
    main()