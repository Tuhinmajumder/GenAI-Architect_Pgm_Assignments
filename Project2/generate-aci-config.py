#!/usr/bin/env python3
import os
import yaml
import json
import subprocess

# Get parameters with defaults
acr_name = os.environ.get('ACR', 'myacrname')
tag = os.environ.get('TAG', 'latest')
location = os.environ.get('LOCATION', 'centralindia')
dns_label = os.environ.get('DNS_LABEL', 'codeopt-app')
img = os.environ.get("IMG","randomuser")
aci = os.environ.get("ACI","codeoptcontainer")
VAULT_NAME = os.environ.get("VAULT_NAME","vaultbdc")
AZURE_CLIENT_SECRET=os.environ.get("AZURE_CLIENT_SECRET","")
AZURE_CLIENT_ID=os.environ.get("AZURE_CLIENT_ID","vaultbdc")
AZURE_TENANT_ID=os.environ.get("AZURE_TENANT_ID","vaultbdc")
AZURE_DEPLOYMENT=os.environ.get("AZURE_DEPLOYMENT","telcogpt")
LANGFUSE_HOST=os.environ.get("LANGFUSE_HOST","https://cloud.langfuse.com")
AZURE_OPENAI_ENDPOINT=os.environ.get("AZURE_OPENAI_ENDPOINT","https://swedencentral.api.cognitive.microsoft.com/")




# Get ACR credentials if not provided
if not os.environ.get('ACR_USERNAME') or not os.environ.get('ACR_PASSWORD'):
    print("Getting ACR credentials...")
    result = subprocess.run(
        f"az acr credential show --name {acr_name} --query \"{{username:username, password:passwords[0].value}}\" -o json",
        shell=True, capture_output=True, text=True
    )
    creds = json.loads(result.stdout)
    acr_username = creds['username']
    acr_password = creds['password']
else:
    acr_username = os.environ.get('ACR_USERNAME')
    acr_password = os.environ.get('ACR_PASSWORD')

# Create the container group definition
container_group = {
    "apiVersion": "2019-12-01",
    "location": location,
    "name": f"{aci}-group",
    "properties": {
        "containers": [
            {
                "name": f"{aci}-frontend",
                "properties": {
                    "image": f"{acr_name}.azurecr.io/{img}-frontend:{tag}",
                    "resources": {
                        "requests": {
                            "cpu": float(os.environ.get('FRONTEND_CPU', '1.0')),
                            "memoryInGB": float(os.environ.get('FRONTEND_MEMORY', '1'))
                        }
                    },
                    "ports": [{"port": 80}],
                    "environmentVariables": [
                        {
                            "name": "BACKEND_URL",
                            "value": os.environ.get('BACKEND_URL', 'http://localhost:8000')
                        },
                    ]
                }
            },
            {
                "name": f"{aci}-backend",
                "properties": {
                    "image": f"{acr_name}.azurecr.io/{img}-backend:{tag}",
                    "resources": {
                        "requests": {
                            "cpu": float(os.environ.get('BACKEND_CPU', '1.0')),
                            "memoryInGB": float(os.environ.get('BACKEND_MEMORY', '2'))
                        }
                    },
                    "ports": [{"port": 8000}],
                    "environmentVariables": [
                        {
                            "name": "BACKEND_URL",
                            "value": os.environ.get('BACKEND_URL', 'http://localhost:8000')
                            
                        },
                        {"name":"VAULT_NAME","value":VAULT_NAME},
                        {"name":"AZURE_CLIENT_SECRET","value":AZURE_CLIENT_SECRET},
                        {"name":"AZURE_CLIENT_ID","value":AZURE_CLIENT_ID},
                        {"name":"AZURE_TENANT_ID","value":AZURE_TENANT_ID},
                        {"name":"AZURE_DEPLOYMENT","value":AZURE_DEPLOYMENT},
                        {"name":"LANGFUSE_HOST","value":LANGFUSE_HOST},
                        {"name":"AZURE_OPENAI_ENDPOINT","value":AZURE_OPENAI_ENDPOINT},
                        {"name":"SESSION_SECRET","value":os.getenv("SESSION_SECRET")},
                        {"name":"RUNNING_IN_AZURE","value":os.getenv("RUNNING_IN_AZURE","false")},
                        {"name":"ALLOWED_ORIGINS","value":os.getenv("ALLOWED_ORIGINS")},

                        
                    ]
                }
            }
        ],
        "osType": "Linux",
        "ipAddress": {
            "type": "Public",
            "ports": [
                {"protocol": "TCP", "port": 80},
                {"protocol": "TCP", "port": 8000}
            ],
            "dnsNameLabel": dns_label
        },
        "imageRegistryCredentials": [
            {
                "server": f"{acr_name}.azurecr.io",
                "username": acr_username,
                "password": acr_password
            }
        ]
    },
    "tags": {},
    "type": "Microsoft.ContainerInstance/containerGroups"
}

# Write to YAML file
with open('container-group.yaml', 'w') as f:
    yaml.dump(container_group, f, default_flow_style=False)

print("Generated container-group.yaml with your parameters")