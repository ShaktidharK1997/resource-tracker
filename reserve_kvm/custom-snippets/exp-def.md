::: {.cell .markdown}
### Define configuration for this experiment (3 VMs)
:::

::: {.cell .markdown}

For this specific experiment, we will need 1 virtual machines connected to a common network. Each of the virtual machines will be of the `m1.large` type, with 4 VCPUs, 8 GB memory, 40 GB disk space.

:::

::: {.cell .code}
```python
username = os.getenv('USER')

node_conf = [
 {'name': "node-0",  'flavor': 'm1.medium', 'image': 'CC-Ubuntu22.04', 'packages': ["virtualenv"]}, 
]
net_conf = [
 {"name": "net0", "subnet": "192.168.1.0/24", "nodes": [{"name": "node-0",   "addr": "192.168.1.10"}]},
]
route_conf = []
```
:::
