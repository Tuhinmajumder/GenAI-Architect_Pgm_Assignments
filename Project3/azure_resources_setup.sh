#!/bin/bash

# Azure RAG System Resources Setup Script
set -e

# Configuration
RESOURCE_GROUP_NAME="rg-smart-ticket-system"
LOCATION="westus2"
STORAGE_ACCOUNT_NAME="problob123"
STORAGE_CONTAINER_NAME="problobdatafiles"
SEARCH_SERVICE_NAME="proactivesearch"
OPENAI_SERVICE_NAME="proactiveservice"
REDIS_CACHE_NAME="procache"
KEY_VAULT_NAME="temp-project-vault"
APP_INSIGHTS_NAME="smart-ticket-insights"
SERVICE_PRINCIPAL_NAME="prompt-flow-key-user"

# Create resource group
az group create --name "$RESOURCE_GROUP_NAME" --location "$LOCATION"

# Create storage account
az storage account create \
    --name "$STORAGE_ACCOUNT_NAME" \
    --resource-group "$RESOURCE_GROUP_NAME" \
    --location "$LOCATION" \
    --sku Standard_LRS \
    --kind StorageV2

# Create blob container
STORAGE_KEY=$(az storage account keys list --resource-group "$RESOURCE_GROUP_NAME" --account-name "$STORAGE_ACCOUNT_NAME" --query '[0].value' -o tsv)
az storage container create \
    --name "$STORAGE_CONTAINER_NAME" \
    --account-name "$STORAGE_ACCOUNT_NAME" \
    --account-key "$STORAGE_KEY"

# Create Azure AI Search service
az search service create \
    --name "$SEARCH_SERVICE_NAME" \
    --resource-group "$RESOURCE_GROUP_NAME" \
    --location "$LOCATION" \
    --sku Standard

# Create Azure OpenAI service
az cognitiveservices account create \
    --name "$OPENAI_SERVICE_NAME" \
    --resource-group "$RESOURCE_GROUP_NAME" \
    --location "$LOCATION" \
    --kind OpenAI \
    --sku S0 \
    --custom-domain "$OPENAI_SERVICE_NAME"

# Deploy models
az cognitiveservices account deployment create \
    --name "$OPENAI_SERVICE_NAME" \
    --resource-group "$RESOURCE_GROUP_NAME" \
    --deployment-name "gpt-4o-mini" \
    --model-name "gpt-4o-mini" \
    --model-version "2024-07-18" \
    --model-format OpenAI \
    --sku-capacity 10 \
    --sku-name "Standard"

az cognitiveservices account deployment create \
    --name "$OPENAI_SERVICE_NAME" \
    --resource-group "$RESOURCE_GROUP_NAME" \
    --deployment-name "text-embedding-ada-002" \
    --model-name "text-embedding-ada-002" \
    --model-version "2" \
    --model-format OpenAI \
    --sku-capacity 10 \
    --sku-name "Standard"

# Create Redis Cache
az redis create \
    --name "$REDIS_CACHE_NAME" \
    --resource-group "$RESOURCE_GROUP_NAME" \
    --location "$LOCATION" \
    --sku Basic \
    --vm-size c0

# Create Key Vault
az keyvault create \
    --name "$KEY_VAULT_NAME" \
    --resource-group "$RESOURCE_GROUP_NAME" \
    --location "$LOCATION" \
    --sku standard

# Create Application Insights
az monitor app-insights component create \
    --app "$APP_INSIGHTS_NAME" \
    --location "$LOCATION" \
    --resource-group "$RESOURCE_GROUP_NAME" \
    --kind web \
    --application-type web

# Create service principal
SP_OUTPUT=$(az ad sp create-for-rbac \
    --name "$SERVICE_PRINCIPAL_NAME" \
    --role Contributor \
    --scopes "/subscriptions/$(az account show --query id -o tsv)/resourceGroups/$RESOURCE_GROUP_NAME")

APP_ID=$(echo $SP_OUTPUT | jq -r '.appId')
PASSWORD=$(echo $SP_OUTPUT | jq -r '.password')
TENANT=$(echo $SP_OUTPUT | jq -r '.tenant')

# Create azure_auth.json
cat > azure_auth.json << EOF
{
  "appId": "$APP_ID",
  "displayName": "$SERVICE_PRINCIPAL_NAME",
  "password": "$PASSWORD",
  "tenant": "$TENANT"
}
EOF

# Set Key Vault access policies
CURRENT_USER_ID=$(az ad signed-in-user show --query id -o tsv)
SP_OBJECT_ID=$(az ad sp show --id "$APP_ID" --query id -o tsv)

az keyvault set-policy \
    --name "$KEY_VAULT_NAME" \
    --object-id "$CURRENT_USER_ID" \
    --secret-permissions get list set delete

az keyvault set-policy \
    --name "$KEY_VAULT_NAME" \
    --object-id "$SP_OBJECT_ID" \
    --secret-permissions get list

# Store secrets in Key Vault
OPENAI_KEY=$(az cognitiveservices account keys list --name "$OPENAI_SERVICE_NAME" --resource-group "$RESOURCE_GROUP_NAME" --query key1 -o tsv)
OPENAI_ENDPOINT=$(az cognitiveservices account show --name "$OPENAI_SERVICE_NAME" --resource-group "$RESOURCE_GROUP_NAME" --query properties.endpoint -o tsv)
SEARCH_KEY=$(az search admin-key show --service-name "$SEARCH_SERVICE_NAME" --resource-group "$RESOURCE_GROUP_NAME" --query primaryKey -o tsv)
SEARCH_ENDPOINT="https://${SEARCH_SERVICE_NAME}.search.windows.net"
REDIS_KEY=$(az redis list-keys --name "$REDIS_CACHE_NAME" --resource-group "$RESOURCE_GROUP_NAME" --query primaryKey -o tsv)
REDIS_HOSTNAME="${REDIS_CACHE_NAME}.redis.cache.windows.net"
REDIS_CONNECTION_STRING="${REDIS_HOSTNAME}:6380,password=${REDIS_KEY},ssl=True,abortConnect=False"
REDIS_URL="rediss://:${REDIS_KEY}@${REDIS_HOSTNAME}:6380"
APP_INSIGHTS_KEY=$(az monitor app-insights component show --app "$APP_INSIGHTS_NAME" --resource-group "$RESOURCE_GROUP_NAME" --query connectionString -o tsv)

az keyvault secret set --vault-name "$KEY_VAULT_NAME" --name "AZURE-OPENAI-API-KEY" --value "$OPENAI_KEY"
az keyvault secret set --vault-name "$KEY_VAULT_NAME" --name "AZURE-OPENAI-ENDPOINT" --value "$OPENAI_ENDPOINT"
az keyvault secret set --vault-name "$KEY_VAULT_NAME" --name "AZURE-SEARCH-ADMIN-KEY" --value "$SEARCH_KEY"
az keyvault secret set --vault-name "$KEY_VAULT_NAME" --name "AZURE-SEARCH-ENDPOINT" --value "$SEARCH_ENDPOINT"
az keyvault secret set --vault-name "$KEY_VAULT_NAME" --name "REDIS-CONNECTION-STRING" --value "$REDIS_CONNECTION_STRING"
az keyvault secret set --vault-name "$KEY_VAULT_NAME" --name "REDIS-URL" --value "$REDIS_URL"
az keyvault secret set --vault-name "$KEY_VAULT_NAME" --name "APPLICATIONINSIGHTS-CONNECTION-STRING" --value "$APP_INSIGHTS_KEY"
az keyvault secret set --vault-name "$KEY_VAULT_NAME" --name "AZURE-STORAGE-ACCOUNT-NAME" --value "$STORAGE_ACCOUNT_NAME"
az keyvault secret set --vault-name "$KEY_VAULT_NAME" --name "AZURE-STORAGE-CONTAINER-NAME" --value "$STORAGE_CONTAINER_NAME"
az keyvault secret set --vault-name "$KEY_VAULT_NAME" --name "AZURE-CLIENT-ID" --value "$APP_ID"
az keyvault secret set --vault-name "$KEY_VAULT_NAME" --name "AZURE-CLIENT-SECRET" --value "$PASSWORD"
az keyvault secret set --vault-name "$KEY_VAULT_NAME" --name "AZURE-TENANT-ID" --value "$TENANT"
az keyvault secret set --vault-name "$KEY_VAULT_NAME" --name "WEAVIATE-URL" --value ""
az keyvault secret set --vault-name "$KEY_VAULT_NAME" --name "WEAVIATE-API-KEY" --value ""

# Create search indexes
curl -X POST \
    "${SEARCH_ENDPOINT}/indexes?api-version=2023-11-01" \
    -H "Content-Type: application/json" \
    -H "api-key: ${SEARCH_KEY}" \
    -d '{
        "name": "active-tickets",
        "fields": [
            {"name": "TicketID", "type": "Edm.String", "key": true, "searchable": false, "filterable": true},
            {"name": "locationID", "type": "Edm.String", "searchable": false, "filterable": true},
            {"name": "description", "type": "Edm.String", "searchable": true, "filterable": false},
            {"name": "estimated_resolution_time", "type": "Edm.String", "searchable": false, "filterable": true},
            {"name": "content_vector", "type": "Collection(Edm.Single)", "searchable": true, "vectorSearchDimensions": 1536, "vectorSearchProfileName": "default"}
        ],
        "vectorSearch": {
            "profiles": [{"name": "default", "algorithm": "hnsw"}],
            "algorithms": [{"name": "hnsw", "kind": "hnsw"}]
        }
    }'

curl -X POST \
    "${SEARCH_ENDPOINT}/indexes?api-version=2023-11-01" \
    -H "Content-Type: application/json" \
    -H "api-key: ${SEARCH_KEY}" \
    -d '{
        "name": "historic-tickets",
        "fields": [
            {"name": "TicketID", "type": "Edm.String", "key": true, "searchable": false, "filterable": true},
            {"name": "locationID", "type": "Edm.String", "searchable": false, "filterable": true},
            {"name": "description", "type": "Edm.String", "searchable": true, "filterable": false},
            {"name": "actual_resolution_time", "type": "Edm.String", "searchable": false, "filterable": true},
            {"name": "content_vector", "type": "Collection(Edm.Single)", "searchable": true, "vectorSearchDimensions": 1536, "vectorSearchProfileName": "default"}
        ],
        "vectorSearch": {
            "profiles": [{"name": "default", "algorithm": "hnsw"}],
            "algorithms": [{"name": "hnsw", "kind": "hnsw"}]
        }
    }'