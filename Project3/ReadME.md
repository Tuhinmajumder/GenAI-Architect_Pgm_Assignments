# Smart Ticket Resolution Estimator

## 📝 Context

In the telecommunications industry, customers highly value timely and transparent communication during service outages. When internet or phone service goes down, customers experience immediate frustration and uncertainty. They urgently want to know if the telecom service provider is aware of the issue, the underlying cause, and when service will be restored. Failure to proactively communicate real-time updates results in increased customer dissatisfaction, higher volumes of support calls, reputational damage, and potential customer churn. 

---

## ❗ Problem Statement

Telecom companies struggle to rapidly collect, interpret, and disseminate accurate outage information at scale. Internal outage data—such as outage cause, impacted regions, and estimated resolution times—is stored in various disconnected systems, including network alarms, support tickets, and field engineer notes. These data sources are not easily accessible or customer friendly. Consequently, support agents are overwhelmed by repetitive outage inquiries, significantly increasing resolution time and customer frustration.

---

## 💡 Proposed Solution

A comprehensive RAG-based ticket processing system that leverages AI to estimate resolution times and generate customer notifications:

* **Backend**: Python-based RAG system using Azure AI Search, Weaviate vector stores, and Azure OpenAI for intelligent ticket processing
* **Frontend**: Streamlit web application providing an intuitive interface for ticket submission and management
* **Architecture**: Multi-tier system with Azure Search indexing blob storage CSV data, optional Weaviate vector search, and Redis caching

The system automatically finds similar historical tickets using hybrid search (text + vector similarity) to provide accurate resolution time estimates and generates empathetic customer service notifications.

---

## 📂 Folder Structure

```
Smart_Ticket_Resolution_Estimator/
├── authorization/
│   ├── authorization.py
│   └── azure_auth.json
├── backend/
│   ├── document_loader.py
│   ├── rag_chain.py
│   └── vector_store.py
├── frontend/
│   └── functions.py
├── app.py
├── azure_resources_setup.sh
├── requirements.txt
└── README.md
```

---

## 🚀 Approach

1. **Azure AI Search Integration**: CSV data from blob storage automatically indexed for fast retrieval
2. **Hybrid Search Strategy**: Combines traditional text search with vector similarity search for optimal relevance
3. **Multi-fallback System**: Intelligent fallback from vector search → hybrid search → text search → global search
4. **Real-time Processing**: Instant ticket processing with resolution time estimation based on historical data
5. **Caching Layer**: Redis caching for improved performance on repeated queries

The system ensures every ticket receives appropriate handling through multiple search strategies with graceful degradation.

---

## 🔧 Prerequisites & Environment Variables

Before you begin, make sure you have:

* Azure CLI logged in (`az login`)
* Python 3.10+ with pip
* Access to Azure OpenAI service
* (optional) Weaviate Cloud instance
* (optional) Redis instance

Export the required variables:

```bash
# Core Azure Resources (Required)
export RESOURCE_GROUP_NAME=rg-smart-ticket-system
export LOCATION=westus2
export STORAGE_ACCOUNT_NAME=problob123
export STORAGE_CONTAINER_NAME=problobdatafiles
export SEARCH_SERVICE_NAME=proactivesearch
export OPENAI_SERVICE_NAME=proactiveservice
export KEY_VAULT_NAME=temp-project-vault

# Optional Services (Enhanced functionality)
export REDIS_CACHE_NAME=procache
export APP_INSIGHTS_NAME=smart-ticket-insights
export WEAVIATE_URL=your-weaviate-cluster-url
export WEAVIATE_API_KEY=your-weaviate-api-key

# Service Principal for Authentication
export SERVICE_PRINCIPAL_NAME=prompt-flow-key-user
export AZURE_CLIENT_ID=xxxxxxxxxxxxx
export AZURE_CLIENT_SECRET=xxxxxxxxxxxxxxxxxxxx
export AZURE_TENANT_ID=xxxxxxxxxxxxxxxxxxxxx
```

---

## 🔐 Resource Provisioning

### 1. Quick Setup with Script

Run the automated setup script:

```bash
chmod +x azure_resources_setup.sh
./azure_resources_setup.sh
```

This script automatically creates:
- Storage account with blob container
- Azure AI Search service with indexes
- Azure OpenAI service with deployments
- Key Vault with secrets
- Redis Cache (optional)
- Application Insights (optional)
- Service Principal with proper permissions

### 2. Manual Setup (Alternative)

#### Create Storage and Search Services

```bash
# Create resource group
az group create --name $RESOURCE_GROUP_NAME --location $LOCATION

# Create storage account
az storage account create \
    --name $STORAGE_ACCOUNT_NAME \
    --resource-group $RESOURCE_GROUP_NAME \
    --location $LOCATION \
    --sku Standard_LRS

# Create Azure AI Search service
az search service create \
    --name $SEARCH_SERVICE_NAME \
    --resource-group $RESOURCE_GROUP_NAME \
    --location $LOCATION \
    --sku Standard
```

#### Create Azure OpenAI Service

```bash
# Create Azure OpenAI service
az cognitiveservices account create \
    --name $OPENAI_SERVICE_NAME \
    --resource-group $RESOURCE_GROUP_NAME \
    --location $LOCATION \
    --kind OpenAI \
    --sku S0

# Deploy required models
az cognitiveservices account deployment create \
    --name $OPENAI_SERVICE_NAME \
    --resource-group $RESOURCE_GROUP_NAME \
    --deployment-name "gpt-4o-mini" \
    --model-name "gpt-4o-mini" \
    --model-version "2024-07-18"

az cognitiveservices account deployment create \
    --name $OPENAI_SERVICE_NAME \
    --resource-group $RESOURCE_GROUP_NAME \
    --deployment-name "text-embedding-ada-002" \
    --model-name "text-embedding-ada-002" \
    --model-version "2"
```

#### Create Key Vault and Store Secrets

```bash
# Create Key Vault
az keyvault create \
    --name $KEY_VAULT_NAME \
    --resource-group $RESOURCE_GROUP_NAME \
    --location $LOCATION

# Store all required secrets (automated by setup script)
```

---

## 🧪 1. Local Development Setup

### Install Dependencies

```bash
# Clone the repository
git clone <your-repo-url>
cd Smart_Ticket_Resolution_Estimator

# Install Python dependencies
pip install -r requirements.txt
```

### Prepare Data Sources

1. **Upload CSV Data**: Upload your ticket CSV files to the blob storage container
2. **Configure Indexers**: Azure Search indexers will automatically process the CSV files
3. **Verify Data**: Check that data appears in Azure AI Search indexes

### Test Individual Components

```bash
# Test document loading
python -c "
from backend.document_loader import TicketDataManager
dm = TicketDataManager('active-tickets', 'historic-tickets')
active_docs = dm.load_active_documents()
print(f'Loaded {len(active_docs)} active tickets')
"

# Test vector store (if Weaviate is configured)
python -c "
from backend.vector_store import VectorStoreManager
vsm = VectorStoreManager('Active_tickets')
print('Vector store connected successfully')
"
```

---

## 🖥️ 2. Running the Application

### Start the Streamlit Application

```bash
# Run the main application
streamlit run app.py
```

### Access the Interface

1. **Browse** **[http://localhost:8501](http://localhost:8501)**
2. **Submit a Ticket**:
   - Select your location ID (1-39)
   - Provide detailed issue description
   - Click "Submit Ticket"
3. **Review Results**:
   - Check estimated resolution time
   - Read customer notification
   - Download ticket details

### System Features

- **🤖 AI-Powered**: Machine learning for smart estimation
- **📊 Historical Analysis**: Learns from past similar tickets  
- **⚡ Real-time Processing**: Instant response and estimation
- **💾 Multi-Search Strategy**: Vector + text + hybrid search
- **🔍 Location-Aware**: Filters by location for relevant matches
- **☁️ Azure Integration**: Full Azure ecosystem integration

---

## 🔍 3. Testing Different Scenarios

### Test with Sample Tickets

```bash
# Example ticket descriptions to test:
# "Email server is down, users cannot access Outlook"
# "WiFi connection is intermittent in the conference room"
# "Printer not responding, showing offline status"
# "Database connection timeout errors in the application"
# "Login authentication failing for multiple users"
```

### Verify Search Strategies

The system automatically tries multiple search approaches:

1. **Vector Search on Active Tickets** (if Weaviate available)
2. **Vector Search on Historic Tickets** (if Weaviate available)  
3. **Azure AI Hybrid Search** (text + vector)
4. **Pure Text Search** (fallback)
5. **Global Search** (no location filter)

### Monitor System Performance

- Check Application Insights for telemetry
- Review Redis cache hit rates
- Monitor Azure Search query performance
- Validate ticket processing accuracy

---

## 🐳 4. Docker Deployment

### Build Docker Image

```bash
# Create Dockerfile
cat > Dockerfile << EOF
FROM python:3.11-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt

COPY . .
EXPOSE 8501

CMD ["streamlit", "run", "app.py", "--server.port=8501", "--server.address=0.0.0.0"]
EOF

# Build image
docker build -t smart-ticket-estimator .
```

### Run Container

```bash
# Run with environment variables
docker run -d -p 8501:8501 \
  -e AZURE_CLIENT_ID=$AZURE_CLIENT_ID \
  -e AZURE_CLIENT_SECRET=$AZURE_CLIENT_SECRET \
  -e AZURE_TENANT_ID=$AZURE_TENANT_ID \
  --name smart-ticket-app \
  smart-ticket-estimator
```

---

## ☁️ 5. Azure Container Instances Deployment

### Create Container Instance

```bash
# Deploy to ACI
az container create \
  --resource-group $RESOURCE_GROUP_NAME \
  --name smart-ticket-aci \
  --image smart-ticket-estimator \
  --ports 8501 \
  --dns-name-label smart-ticket-app \
  --environment-variables \
    AZURE_CLIENT_ID=$AZURE_CLIENT_ID \
    AZURE_CLIENT_SECRET=$AZURE_CLIENT_SECRET \
    AZURE_TENANT_ID=$AZURE_TENANT_ID \
    RUNNING_IN_AZURE=True
```

### Access Application

```bash
# Get public URL
az container show \
  --resource-group $RESOURCE_GROUP_NAME \
  --name smart-ticket-aci \
  --query ipAddress.fqdn -o tsv
```

Browse to: **http://smart-ticket-app.{region}.azurecontainer.io:8501**

---

## 📊 6. Data Management & CSV Structure

### Required CSV Format

**Active Tickets (active-tickets index):**
```csv
TicketID,locationID,description,estimated_resolution_time,customerID
1001,15,"Email server connectivity issues",24,C001
1002,23,"Printer not responding to print jobs",4,C002
```

**Historic Tickets (historic-tickets index):**
```csv
TicketID,locationID,description,actual_resolution_time,customerID
H001,15,"Email server was down due to DNS issues",18,C001
H002,23,"Printer driver needed updating",2,C002
```

### Upload Data to Blob Storage

```bash
# Upload CSV files to blob storage
az storage blob upload \
  --account-name $STORAGE_ACCOUNT_NAME \
  --container-name $STORAGE_CONTAINER_NAME \
  --name active_tickets.csv \
  --file ./data/active_tickets.csv

az storage blob upload \
  --account-name $STORAGE_ACCOUNT_NAME \
  --container-name $STORAGE_CONTAINER_NAME \
  --name historic_tickets.csv \
  --file ./data/historic_tickets.csv
```

### Verify Indexing

```bash
# Check if data was indexed
az search query \
  --service-name $SEARCH_SERVICE_NAME \
  --index-name active-tickets \
  --search-text "*"
```

---

## 🔧 7. Configuration & Troubleshooting

### Environment Validation

The application automatically validates required configuration:

```bash
# Test configuration
python -c "
from frontend.functions import validate_environment
if validate_environment():
    print('✅ Configuration is valid')
else:
    print('❌ Configuration issues detected')
"
```

### Common Issues

| Issue | Solution |
|-------|----------|
| "No tickets found in search index" | Verify CSV files are uploaded and indexed |
| "Failed to create embeddings" | Check Azure OpenAI endpoint and API key |
| "Vector store unavailable" | Verify Weaviate URL and API key (optional) |
| "Redis connection failed" | Check Redis connection string (optional) |

### Debug Logging

Enable detailed logging:

```python
import logging
logging.basicConfig(level=logging.DEBUG)
```

---

## 📈 8. Monitoring & Analytics

### Application Insights Integration

View telemetry in Azure Portal:
- Ticket processing metrics
- Search performance analytics
- Error tracking and debugging
- User interaction patterns

### Performance Metrics

Key metrics to monitor:
- **Resolution Time Accuracy**: Compare estimates vs actual times
- **Search Strategy Success**: Which search methods find matches
- **Response Time**: End-to-end ticket processing speed
- **Cache Hit Rate**: Redis cache effectiveness

---

## 🧹 Cleanup & Teardown

When done with testing, clean up Azure resources:

```bash
# Delete specific resources
az container delete --resource-group $RESOURCE_GROUP_NAME --name smart-ticket-aci --yes
az search service delete --resource-group $RESOURCE_GROUP_NAME --name $SEARCH_SERVICE_NAME --yes
az cognitiveservices account delete --name $OPENAI_SERVICE_NAME --resource-group $RESOURCE_GROUP_NAME
az storage account delete --name $STORAGE_ACCOUNT_NAME --resource-group $RESOURCE_GROUP_NAME --yes
az keyvault delete --name $KEY_VAULT_NAME --resource-group $RESOURCE_GROUP_NAME

# Optional: Delete entire resource group
az group delete --name $RESOURCE_GROUP_NAME --yes --no-wait
```

### Local Cleanup

```bash
# Remove Python cache
find . -type d -name "__pycache__" -exec rm -rf {} +
find . -name "*.pyc" -delete

# Remove Docker containers
docker stop smart-ticket-app
docker rm smart-ticket-app
docker rmi smart-ticket-estimator
```

---

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Add tests for new functionality
5. Submit a pull request

---

## 🆘 Support

For issues and questions:
- Check the troubleshooting section above
- Review Azure service logs in the portal
- Enable debug logging for detailed error information
- Consult Azure AI Search and OpenAI documentation

---

*Smart Ticket Resolution Estimator - Powered by Azure AI Search, OpenAI, and Weaviate*
