::: {.cell .markdown}
## Set up Docker
:::

::: {.cell .code}
```python
remote = chi.ssh.Remote(server_ips[0])
```
:::

::: {.cell .code}
```python
remote.run("sudo apt-get update")
remote.run("sudo apt-get install -y apt-transport-https ca-certificates curl software-properties-common")
```
:::

::: {.cell .code}
```python
remote.run("curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo gpg --dearmor -o /usr/share/keyrings/docker-archive-keyring.gpg")
remote.run('echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/docker-archive-keyring.gpg] https://download.docker.com/linux/ubuntu $(lsb_release -cs) stable" | sudo tee /etc/apt/sources.list.d/docker.list > /dev/null')
```
:::


::: {.cell .code}
```python
remote.run("sudo apt-get update")
remote.run("sudo apt-get install -y docker-ce docker-ce-cli containerd.io")
```
:::


::: {.cell .code}
```python
remote.run('sudo groupadd -f docker; sudo usermod -aG docker $USER')
remote.run("sudo chmod 666 /var/run/docker.sock")
```
:::

::: {.cell .code}
```python
# check configuration
remote.run("docker run hello-world")
```
:::

::: {.cell .code}
```python
# install Python libraries required for resource tracking
remote.run("git clone https://github.com/ShaktidharK1997/resource-tracker.git")
remote.run("cd resource-tracker; pip3 install -r requirements.txt")
```
:::

::: {.cell .code}
```python
# install docker compose 
# Download the docker compose plugin
remote.run("sudo curl -L https://github.com/docker/compose/releases/download/v2.24.5/docker-compose-linux-x86_64 -o /usr/local/bin/docker-compose")

# Make it executable
remote.run("sudo chmod +x /usr/local/bin/docker-compose")

# Verify the installation
remote.run("docker-compose --version")
# Use docker to setup pgsql container with required tables 
remote.run("cd resource-tracker; docker-compose up -d")
```
:::

::: {.cell .markdown}
## Authentication Setup Instructions
### 1. Create Application Credentials

- Log into the Chameleon dashboard for your site (KVM@TACC or UC)

- Navigate to Identity → Application Credentials

- Click "Create Application Credential"

Fill in the details:

- Name: Give it a descriptive name (e.g., "resource-tracker-auth")

- Role: Select "member"

- Expiration: Set according to your needs

!! Important: Download the credentials file when prompted - you'll need this information

### 2. Configure the Resource Tracker

Get the VM's IP address (you can find this in the output of print(server_ips))
SSH into the VM:

```bash
ssh cc@<VM_IP_ADDRESS>
```

Configure Openstack and Blazar Authentication : 

- Open .env file present in resource_tracker folder

```bash
cd resource-tracker
nano .env
```

- Configure the credentials in the .env file:
```sh
# OpenStack credentials for normal resources
OS_AUTH_URL= # site that you want to track
OS_APPLICATION_CREDENTIAL_ID=
OS_APPLICATION_CREDENTIAL_SECRET=

BLAZAR_AUTH_URL=
BLAZAR_APPLICATION_CREDENTIAL_ID=
BLAZAR_APPLICATION_CREDENTIAL_SECRET=
```
:::


::: {.cell .markdown}
## Setting up a cron job for resource tracking
:::

::: {.cell .code}
```python
remote.run("""
cd resource-tracker
chmod +x install_cron.sh
./install_cron.sh
""")
```
:::

::: {.cell .markdown}
## Resource search

Usage: python3 resource_search.py query_string 

Arguments:

  query_string      
  
    Required: Search the resource database for resource names with the particular query_string
  
    Example: 'track' will return resources having 'track' as a substring in the resource name.
:::

::: {.cell .code}
```python
remote.run('cd resource-tracker; python3 resource_search.py "track"')
```
:::


::: {.cell .markdown}
## Resource cleanup

Usage: python3 resource_cleanup.py HOURS [--dry-run]

Arguments:

  HOURS        Required: Delete resources older than this many hours
               Example: '24' will find resources running for more than 24 hours

Options:
  --dry-run    Optional: Preview mode that shows which resources would be deleted
               without actually deleting them. Useful for verification.
    
> ⚠️ WARNING: Running without --dry-run will permanently delete the identified resources!

:::

::: {.cell .code}
```python
remote.run("cd resource-tracker; python3 resource_cleanup.py 24 --dry-run")
```
:::
