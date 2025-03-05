# Resource Tracker for Chameleon Cloud

## Overview

Resource Tracker is a comprehensive system designed to monitor, track, and manage OpenStack resources in Chameleon Cloud environments. It helps administrators and users keep track of their cloud resources, identify stale resources, and implement automated cleanup procedures to prevent resource wastage.

## Key Features

- **Resource Tracking**: Monitors various OpenStack resources including servers, networks, subnets, routers, floating IPs, and GPU leases
- **Multi-Site Support**: Works across different Chameleon project sites (KVM@TACC, CHI@TACC, CHI@UC)
- **Resource History**: Maintains historical data of resources, including creation time, status changes, and deletion
- **Resource Search**: Easily search for resources by name across all resource types
- **Resource Cleanup**: Automate the cleanup of stale or unused resources based on age or other criteria

## Components

The Resource Tracker consists of three main Python scripts:

1. **resource_tracker.py**: Core tracking service that monitors OpenStack resources and maintains the database
2. **resource_search.py**: Utility to search for resources by name
3. **resource_cleanup.py**: Tool to identify and clean up stale resources

## Installation

### Using Docker (Recommended)

1. Clone the repository:
   ```bash
   git clone https://github.com/ShaktidharK1997/resource-tracker.git
   cd resource-tracker
   ```

2. Configure environment variables in the `.env` file:
   ```
   # Database configuration
   DB_NAME=resource_tracker
   DB_USER=postgres
   DB_PASSWORD=password
   DB_HOST=db
   DB_PORT=5432

   # OpenStack credentials
   OS_AUTH_URL=https://kvm.tacc.chameleoncloud.org:5000/v3,https://chi.tacc.chameleoncloud.org:5000/v3,https://chi.uc.chameleoncloud.org:5000/v3
   OS_APPLICATION_CREDENTIAL_ID=your_credential_id1,your_credential_id2,your_credential_id3
   OS_APPLICATION_CREDENTIAL_SECRET=your_secret1,your_secret2,your_secret3

   # Blazar credentials (for GPU lease tracking)
   BLAZAR_AUTH_URL=https://chi.tacc.chameleoncloud.org:5000/v3,https://chi.uc.chameleoncloud.org:5000/v3
   BLAZAR_APPLICATION_CREDENTIAL_ID=your_blazar_credential_id1,your_blazar_credential_id2
   BLAZAR_APPLICATION_CREDENTIAL_SECRET=your_blazar_secret1,your_blazar_secret2
   ```

3. Start the services using Docker Compose:
   ```bash
   docker-compose up -d
   ```

### Manual Installation

1. Clone the repository:
   ```bash
   git clone https://github.com/ShaktidharK1997/resource-tracker.git
   cd resource-tracker
   ```

2. Install required Python packages:
   ```bash
   pip install -r requirements.txt
   ```

3. Set up a PostgreSQL database and configure the `.env` file as described above.

4. Set up database tables (schema is provided in the repository).

## Usage

### Resource Tracking

The resource tracker runs as a background service, periodically collecting data about OpenStack resources. It's recommended to set it up as a cron job:

```bash
cd resource-tracker/scripts
chmod +x install_cron.sh
./install_cron.sh
```

This will install a cron job to run the tracker every hour.

### Resource Search

Search for resources by name:

```bash
python resource_search.py <query_string> [--site SITE]
```

Examples:
```bash
# Search for all resources with "test" in their name
python resource_search.py "test"

# Search for resources with "web" and "server" in their name
python resource_search.py "web*server"

# Search for resources with "database" in their name on a specific site
python resource_search.py "database" --site "chi@tacc"
```

### Resource Cleanup

Identify and clean up stale resources:

```bash
python resource_cleanup.py <hours> [--dry-run] [--resource-type TYPE] [--site SITE]
```

Examples:
```bash
# Preview resources older than 24 hours (dry run)
python resource_cleanup.py 24 --dry-run

# Delete servers older than 48 hours
python resource_cleanup.py 48 --resource-type servers

# Delete all resource types older than 72 hours at a specific site
python resource_cleanup.py 72 --site "kvm@tacc"
```

**⚠️ WARNING**: Running without `--dry-run` will permanently delete the identified resources!

## Chameleon Cloud Integration

Resource Tracker is specifically designed for Chameleon Cloud environments. It handles the unique aspects of Chameleon's implementation of OpenStack, including:

- Multi-site management (KVM@TACC, CHI@TACC, CHI@UC)
- GPU lease tracking via Blazar
- Protection of essential infrastructure resources

## Project Structure

```
resource-tracker/
├── resource_tracker.py     # Core tracking service
├── resource_search.py      # Resource search utility
├── resource_cleanup.py     # Resource cleanup tool
├── scripts/
│   └── install_cron.sh     # Script to install cron job
├── docker-compose.yml      # Docker Compose configuration
├── requirements.txt        # Python dependencies
└── README.md               # This file
```

## Extending the Tracker

The Resource Tracker is designed to be modular and extensible. To add tracking for new resource types:

1. Add appropriate database tables for the new resource type
2. Extend the `ResourceTracker` class to fetch and update data for the new resource type
3. Update the search and cleanup scripts to include the new resource type
