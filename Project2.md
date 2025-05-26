# Code Optimization Assistant

## 📝 Overview

A two-tier app:

* **Backend**: FastAPI that clones GitHub repos, enforces guardrails, calls Azure OpenAI + Langfuse.
* **Frontend**: React + Vite SPA that drives the UX, talking to `/api` endpoints.

By always routing the SPA’s `/api` calls to the same origin—via Vite proxy locally, nginx in Docker, or Azure Front Door in ACI—we avoid CORS and SameSite cookie issues.

---

## 📂 Folder Structure

```
code-optimizer/
├── backend/
│   ├── main.py
│   ├── prompt_setup.py
│   ├── secrets.py
│   ├── guardrails.py
│   ├── optimizers.py
│   ├── utils.py
│   ├── requirements.txt
│   └── backend.Dockerfile
└── frontend/
    ├── package.json
    ├── frontend.Dockerfile
    ├── vite.config.js
    └── src/
        ├── api.js
        └── App.jsx
```

---

## 🚀 Approach

1. **Same-origin `/api`**: SPA always calls `/api/...`.
2. **Local dev**: Vite proxies `/api` → `localhost:8000`.
3. **Docker**: nginx in front-end container proxies `/api` → backend container.
4. **ACI + Front Door**: Front Door routes `/` → front-end ACI, `/api/*` → backend ACI.

Cookies (`SameSite=Lax`) flow seamlessly because the browser never sees a cross-site request.

---

## 🔧 Prerequisites & Environment Variables

Before you begin, make sure you have:

* Azure CLI logged in (`az login`)
* Docker (for local container mode)
* Node.js & npm (for local React)

Export the standard variables:

```bash
export NAME=anshu
export RG=Tredence-Batch2
export VAULT=vault$NAME
export VAULT_NAME=$VAULT
export SP=sp$NAME
export ACR=codeacr$NAME
export ACI=aci$NAME
export IMG=img$NAME

# Your Azure/OpenAI/Langfuse creds
export AOAIKEY=xxxxxxxxxxxxxxxxxxxxx
export LFPUBLIC=xxxxxxxxxxxxxxxxxxxxx
export LFSECRET=xxxxxxxxxxxxxxxxxxxxxxxxxx
export AZURE_DEPLOYMENT=telcogpt2
export LANGFUSE_HOST=https://cloud.langfuse.com
export AZURE_OPENAI_ENDPOINT=https://swedencentral.api.cognitive.microsoft.com/
export REGION=centralindia

# Cookie/session settings
export SESSION_SECRET=$(openssl rand -base64 32)
export RUNNING_IN_AZURE=False
export COOKIE_SECURE=False

# For local React & Docker mode
export VITE_API_URL=http://localhost:8000
```

---

## 🔐 Resource Provisioning

These commands set up Key Vault, Service Principal, ACR.

### 1. Create Azure Key Vault

```bash
az keyvault create -g $RG -n $VAULT --enable-rbac-authorization true
```

### 2. Add Secrets to Key Vault

```bash
az keyvault secret set --vault-name $VAULT -n LANGFUSE-PUBLIC-KEY  --value $LFPUBLIC  
az keyvault secret set --vault-name $VAULT -n LANGFUSE-SECRET-KEY  --value $LFSECRET  
az keyvault secret set --vault-name $VAULT -n AZURE-OPENAI-API-KEY --value $AOAIKEY  
```

### 3. Create Service Principal for Key Vault Access

```bash
az ad sp create-for-rbac -n $SP \
  --role "Key Vault Secrets User" \
  --scopes $(az keyvault show -n $VAULT --query id -o tsv) \
  --sdk-auth > sp.json
```

*Extract `clientId`, `clientSecret`, `tenantId` from `sp.json` into env vars:*

```bash
export AZURE_CLIENT_ID=xxxxxxxxxxxxx
export AZURE_CLIENT_SECRET=xxxxxxxxxxxxxxxxxxxx
export AZURE_TENANT_ID=xxxxxxxxxxxxxxxxxxxxx
```

### 4. Create & Login to Azure Container Registry

```bash
az acr create -g $RG -n $ACR --sku Basic  
az acr update -n $ACR --admin-enabled true  

# login to ACR
az acr login -n $ACR
```

---

## 🧪 1. Local Python Backend

1. **Go** into the backend folder:

   ```bash
   cd code-optimizer/backend
   ```
2. **Run** the FastAPI server:

   ```bash
   uvicorn main:app --reload --port 8000
   ```
3. **Test** via Swagger UI:

   * Browse **[http://localhost:8000/docs](http://localhost:8000/docs)**
   * **POST** `/session` → **200 OK**, look for `Set-Cookie`
   * **POST** `/clone` with JSON

     ```json
     { "repo_url": "https://github.com/Bluedata-Consulting/Talent_assessment_assistant-demo" }
     ```
   * **GET** `/file?relative_path=<one-of-the-files>`
   * **POST** `/optimise` with your code + optional feedback

---

## 🖥️ 2. Local React Frontend

1. **Open** a new terminal, go to:

   ```bash
   cd code-optimizer/frontend
   ```
2. **Install** deps (first time):

   ```bash
   # delete the directory node_modules
   npm install
   ```
3. **Start** Vite dev server:

   ```bash
   npm run dev
   ```
4. **Browse** **[http://localhost:5173](http://localhost:5173)**

   * **Paste** the demo repo URL → https://github.com/Bluedata-Consulting/Talent_assessment_assistant-demo **Clone**
   * **Select** a file → **Load**
   * **Click** **Optimise** → optimized code appears

---

## 🐳 3. Local Docker (Backend + Frontend)

### Backend Container

```bash
# build
sudo docker build -f backend.Dockerfile -t $IMG-backend:latest .

# run
sudo docker run -d -p 8000:8000 \
  -e AZURE_CLIENT_SECRET=$AZURE_CLIENT_SECRET \
  -e AZURE_CLIENT_ID=$AZURE_CLIENT_ID \
  -e AZURE_TENANT_ID=$AZURE_TENANT_ID \
  -e VAULT_NAME=$VAULT \
  -e SESSION_SECRET=$SESSION_SECRET \
  -e AZURE_DEPLOYMENT=$AZURE_DEPLOYMENT \
  -e RUNNING_IN_AZURE=False \
  -e LANGFUSE_HOST=$LANGFUSE_HOST \
  -e AZURE_OPENAI_ENDPOINT=$AZURE_OPENAI_ENDPOINT \
  -e COOKIE_SECURE=false \
  -e ALLOWED_ORIGINS=http://localhost:8080 \
  --name codeopt-backend \
  $IMG-backend:latest
```

**Verify**: Swagger at **[http://localhost:8000/docs](http://localhost:8000/docs)**

### Frontend Container

```bash
# build (pointing at your local backend)
sudo docker build -f frontend.Dockerfile \
  --build-arg BACKEND_HOST=localhost \
  -t $IMG-frontend:latest .

# run
sudo docker run -d -p 8080:80 \
  --add-host=host.docker.internal:host-gateway \
  --name codeopt-frontend \
  -e BACKEND_URL=http://host.docker.internal:8000 \
  $IMG-frontend:latest

#check docker images
sudo docker images -a

# delete all docker images
sudo docker rmi $(sudo docker images -aq)

# check all containers
sudo docker ps -a

# delete all containers
sudo docker rm $(sudo docker ps -aq)


```

**Test**: open **[http://localhost:8080](http://localhost:8080)** and repeat clone/load/optimise.

---

## ☁️ 4. Azure Container Instances (Single ACI Group)

0. **Push** docker images to ACR:

   ```bash
   # login to ACR
   ACR_USERNAME=$(az acr credential show --name $ACR --query "username" -o tsv)
   ACR_PASSWORD=$(az acr credential show --name $ACR --query "passwords[0].value" -o tsv)

   sudo az acr login -n $ACR -u $ACR_USERNAME -p $ACR_PASSWORD

   # push backend image to ACR

   sudo docker tag $IMG-backend:latest $ACR.azurecr.io/$IMG-backend:latest
   sudo docker push $ACR.azurecr.io/$IMG-backend:latest


   # push frontend image to ACR

   sudo docker tag $IMG-frontend:latest $ACR.azurecr.io/$IMG-frontend:latest
   sudo docker push $ACR.azurecr.io/$IMG-frontend:latest

   # list all the docker images in ACR
   az acr repository list -n $ACR -o table
   ```

1. **Regenerate** ACI YAML if needed:

   ```bash

   export SESSION_SECRET=$(openssl rand -base64 32)
   export RUNNING_IN_AZURE=True
   export COOKIE_SECURE=True
   export TAG=latest
   export DNS_LABEL=codeopt-app
   export LOCATION=$REGION
   export ALLOWED_ORIGINS=http://$DNS_LABEL.$LOCALTION.azurecontainer.io,http://localhost
   python generate-aci-config.py
   ```
2. **Deploy** both containers in one group:

   ```bash
   az container create -g $RG --file container-group.yaml
   ```
3. **Get** the public FQDN:

   ```bash
   az container show -g $RG -n ${ACI}-group \
     --query "ipAddress.fqdn" -o tsv
   ```
4. **Backend Test**:

   * Browse **http\://<ACI-FQDN>:8000/docs** → `/session`, `/clone`, `/optimise`
5. **Frontend Test**:

   * Browse **http\://<ACI-FQDN>** → clone/load/optimise against the ACI backend

---

## 🧹 Cleanup & Teardown

When you’re done, delete all Azure resources to avoid charges:

```bash
# Remove ACI group
az container delete -g $RG -n ${ACI}-group --yes

# Delete ACR
az acr delete -g $RG -n $ACR --yes

# Delete Key Vault
az keyvault delete -n $VAULT -g $RG

# (Optional) Delete Service Principal
az ad sp delete --id $(az ad sp list --display-name $SP --query "[0].id" -o tsv)

# (Optional) Delete Resource Group if dedicated
# az group delete -g $RG --yes --no-wait
```

---
