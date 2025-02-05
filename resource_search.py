import logging
from datetime import datetime
from typing import List, Dict, Any
import sys
from resource_tracker import ResourceTracker  # Import the ResourceTracker class
import os
from dotenv import load_dotenv 
import argparse


load_dotenv()


logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('resource_search.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)
def search_resources_by_name(tracker: ResourceTracker, search_string: str) -> Dict[str, List[Dict[str, Any]]]:
    """Search for resources with names containing the given substring."""
    results = {
        'servers': [],
        'networks': [],
        'routers': [],
        'subnets': [],
        'leases': []
    }

    try:
        # Get database connection
        conn = tracker.get_db_connection()
        try:
            with conn.cursor() as cur:
                # Search servers
                cur.execute("""
                    SELECT resource_id, resource_name, created_time, last_seen_time
                    FROM servers
                    WHERE resource_name LIKE %s
                """, (f'%{search_string}%',))
                results['servers'] = [{
                    'resource_id': row[0],
                    'resource_name': row[1],
                    'created_time': row[2],
                    'last_seen_time': row[3]
                } for row in cur.fetchall()]

                # Search networks
                cur.execute("""
                    SELECT resource_id, resource_name, created_time, last_seen_time
                    FROM networks
                    WHERE resource_name LIKE %s
                """, (f'%{search_string}%',))
                results['networks'] = [{
                    'resource_id': row[0],
                    'resource_name': row[1],
                    'created_time': row[2],
                    'last_seen_time': row[3]
                } for row in cur.fetchall()]

                # Search routers
                cur.execute("""
                    SELECT resource_id, resource_name, created_time, last_seen_time
                    FROM routers
                    WHERE resource_name LIKE %s
                """, (f'%{search_string}%',))
                results['routers'] = [{
                    'resource_id': row[0],
                    'resource_name': row[1],
                    'created_time': row[2],
                    'last_seen_time': row[3]
                } for row in cur.fetchall()]

                # Search subnets
                cur.execute("""
                    SELECT resource_id, resource_name, created_time, last_seen_time
                    FROM subnets
                    WHERE resource_name LIKE %s
                """, (f'%{search_string}%',))
                results['subnets'] = [{
                    'resource_id': row[0],
                    'resource_name': row[1],
                    'created_time': row[2],
                    'last_seen_time': row[3]
                } for row in cur.fetchall()]

                # Search GPU leases
                cur.execute("""
                    SELECT lease_id, lease_name, created_time, last_seen_time
                    FROM gpu_leases
                    WHERE lease_name LIKE %s
                """, (f'%{search_string}%',))
                results['leases'] = [{
                    'lease_id': row[0],
                    'lease_name': row[1],
                    'created_time': row[2],
                    'last_seen_time': row[3]
                } for row in cur.fetchall()]

        except Exception as e:
            logger.error(f"Error searching resources: {str(e)}")
            raise
        finally:
            conn.close()

    except Exception as e:
        logger.error(f"Failed to search resources: {str(e)}")
        raise

    return results

def main():

    parser = argparse.ArgumentParser(description = 'Parser for resource-search script')
    parser.add_argument("query_string", type=str, help ='The query string you want to search resource tracker with')
    args = parser.parse_args()

    # Database connection parameters
    db_params = {
        'dbname': os.getenv('DB_NAME'),
        'user': os.getenv('DB_USER'),
        'password': os.getenv('DB_PASSWORD'),
        'host': os.getenv('DB_HOST'),
        'port': os.getenv('DB_PORT')
    }

    # Initialize the ResourceTracker
    tracker = ResourceTracker(db_params, {}, {})

    # Search for resources
    results = search_resources_by_name(tracker, args.query_string)

    # Print the results
    
    tracker.display_resources(results)
if __name__ == "__main__":
    main()