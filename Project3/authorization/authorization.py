from azure.identity import ClientSecretCredential
from azure.keyvault.secrets import SecretClient
import json
 
def retrive_credential(secret_name):
    key_vault_name = "temp-project-vault"  # Replace with your vault name
    vault_url = f"https://{key_vault_name}.vault.azure.net"
 
    # Load the Service Principal credentials from the JSON file
    with open('azure_auth.json') as f:
        creds = json.load(f)
 
    client_id = creds['appId']
    client_secret = creds['password']
    tenant_id = creds['tenant']
 
    credential = ClientSecretCredential(
                tenant_id=tenant_id,
                client_id=client_id,
                client_secret=client_secret
            )
 
    client = SecretClient(vault_url=vault_url, credential=credential)
 
    retrieved_secret = client.get_secret(secret_name)
    key = retrieved_secret.value
    return key