# Smart Ticket Resolution Estimator - Complete Process Flow

## 📋 Step-by-Step Process Flow

### Phase 1: System Initialization

#### Step 1: Application Startup (`app.py::main()`)
```python
1. Set Streamlit page configuration
2. Initialize Application Insights telemetry
3. Validate environment variables
4. Check system readiness status
```

#### Step 2: Environment Validation (`functions.py::validate_environment()`)
```python
Required Variables Check:
├── AZURE-OPENAI-ENDPOINT ✓
├── AZURE-SEARCH-ENDPOINT ✓  
├── AZURE-SEARCH-ADMIN-KEY ✓
└── Optional variables logged if missing

Return: True/False for system readiness
```

#### Step 3: System Component Initialization (`functions.py::AppInitializer.initialize_system()`)

**Sub-step 3a: Create Embeddings Model**
```python
AppInitializer.create_embeddings():
├── Retrieve Azure OpenAI endpoint from Key Vault
├── Setup DefaultAzureCredential for authentication
├── Create AzureOpenAIEmbeddings instance
│   ├── Model: text-embedding-ada-002
│   ├── API Version: 2024-06-01
│   └── Token provider with AAD authentication
└── Return configured embeddings model
```

**Sub-step 3b: Load Ticket Data**
```python
AppInitializer.load_ticket_data():
├── Create TicketDataManager(ACTIVE_INDEX, HISTORIC_INDEX)
├── Load active documents from Azure Search
│   └── DocumentLoader processes "active-tickets" index
├── Load historic documents from Azure Search  
│   └── DocumentLoader processes "historic-tickets" index
└── Return (data_manager, active_docs, historic_docs)
```

**Sub-step 3c: Setup Vector Stores**
```python
AppInitializer.setup_vector_stores():
├── Try connecting to Weaviate for active tickets
│   ├── VectorStoreManager("Active_tickets")
│   ├── Check collection exists/create if needed
│   └── Populate with active documents if empty
├── Try connecting to Weaviate for historic tickets
│   ├── VectorStoreManager("Historic_tickets") 
│   ├── Check collection exists/create if needed
│   └── Populate with historic documents if empty
├── Handle graceful degradation if Weaviate unavailable
└── Return (active_vsm, historic_vsm, collections)
```

**Sub-step 3d: Create Ticket Processor**
```python
TicketProcessor initialization:
├── Setup Azure AI Search client
├── Setup Azure OpenAI LLM (gpt-4o-mini)
├── Setup Redis client (optional)
├── Create prompt templates for notifications
├── Discover vector field name in search index
└── Configure multi-search capabilities
```

---

### Phase 2: User Interface & Input Handling

#### Step 4: Display User Interface (`functions.py::display_ticket_form()`)
```python
Streamlit Form Components:
├── Location ID selector (1-39)
├── Issue description text area
├── Submit button
└── Form validation on submission
```

#### Step 5: Input Validation
```python
Validation Rules:
├── LocationID: Must be selected (not None)
├── Description: Not empty, minimum 20 characters
├── Description: Stripped of whitespace
└── Error messages for invalid inputs
```

---

### Phase 3: Ticket Processing Engine

#### Step 6: Ticket Request Processing (`rag_chain.py::process_ticket_request()`)

**Sub-step 6a: Initial Validation & Setup**
```python
Process Flow:
├── Validate query (minimum 20 characters)
├── Generate cache key (SHA256 hash)
├── Check Redis cache for existing result
├── Get next available ticket and customer IDs
└── Initialize search strategy sequence
```

**Sub-step 6b: Multi-Strategy Search Sequence**

**Strategy 1: Vector Search on Active Tickets**
```python
IF active_vectorstore available:
├── _search_vector_store(description, active_vectorstore, locationID)
├── Generate embeddings for description
├── Weaviate similarity search with location filter
├── Return documents with similarity scores
└── IF matches found → Calculate time & create ticket
```

**Strategy 2: Vector Search on Historic Tickets**
```python
IF no active matches AND historic_vectorstore available:
├── _search_vector_store(description, historic_vectorstore, locationID)
├── Search historic tickets for similar resolved issues
├── Use actual_resolution_time for time estimation
└── IF matches found → Calculate time & create ticket
```

**Strategy 3: Azure AI Hybrid Search**
```python
IF no vector matches:
├── _search_azure_hybrid(description, locationID)
├── Combine text search + vector search in Azure
│   ├── Generate embedding vector if available
│   ├── Create vector query for hybrid search
│   └── Fallback to text-only if vector fails
├── Filter by locationID
└── IF matches found → Calculate time & create ticket
```

**Strategy 4: Pure Text Search**
```python
IF hybrid search fails:
├── _search_azure_text_only(description, locationID)
├── Full-text search with advanced query processing
├── Use search_mode="all" and query_type="full"
└── IF matches found → Calculate time & create ticket
```

**Strategy 5: Global Search (No Location Filter)**
```python
IF location-specific search fails:
├── Search without location filter
├── Use broader dataset for matching
└── IF matches found → Calculate time & create ticket
```

**Strategy 6: Invalid Query Response**
```python
IF no matches in any strategy:
├── Create invalid_query ticket type
├── Set estimated_resolution_time = 0
├── Generate helpful feedback message
└── Request more specific details
```

#### Step 7: Resolution Time Calculation (`rag_chain.py::_calculate_estimated_time()`)
```python
Time Calculation Logic:
├── Extract resolution times from similar tickets
│   ├── estimated_resolution_time (for active tickets)
│   └── actual_resolution_time (for historic tickets)
├── Convert string values to float, handle errors
├── Calculate average time using numpy.mean()
├── Default to 24 hours if no valid times
└── Return integer hours for estimation
```

#### Step 8: Ticket Creation (`rag_chain.py::_create_ticket()`)
```python
Ticket Structure:
├── TicketID: Auto-generated unique ID
├── customerID: Auto-generated customer ID  
├── locationID: User-provided location
├── type: "complaint" (standard)
├── description: Summarized if > 1500 chars
├── clusterID: 5 (default cluster)
└── estimated_resolution_time: Calculated hours
```

---

### Phase 4: AI-Powered Content Generation

#### Step 9: Customer Notification Generation (`rag_chain.py::_generate_notification()`)
```python
Notification Process:
├── Create prompt with ticket details
│   ├── Issue description
│   ├── Estimated resolution time
│   ├── Location ID
│   └── Search method used
├── Send to Azure OpenAI GPT-4o-mini
├── Generate empathetic, professional message
└── Fallback to template if AI generation fails
```

#### Step 10: Text Summarization (if needed)
```python
IF description > 1500 characters:
├── Use summarization prompt template
├── Send to Azure OpenAI for concise summary
├── Preserve key technical details
└── Fallback to truncation if summarization fails
```

---

### Phase 5: Data Persistence & Caching

#### Step 11: Store Ticket in Search Index (`rag_chain.py::add_ticket_to_search()`)
```python
Azure Search Storage:
├── Format ticket as search document
├── Generate content vector if embeddings available
├── Upload document to active-tickets index
└── Enable future similarity searches
```

#### Step 12: Store Ticket in Vector Store (`vector_store.py::add_single_document()`)
```python
IF Weaviate available:
├── Validate required fields
├── Generate embedding vector
├── Store in appropriate collection
└── Log success/failure
```

#### Step 13: Cache Results (`rag_chain.py::_cache_result()`)
```python
IF Redis available:
├── Serialize result as JSON
├── Store with TTL (1 hour default)
├── Use query hash as cache key
└── Handle cache failures gracefully
```

---

### Phase 6: Results Display & User Experience

#### Step 14: Display Ticket Information (`functions.py::display_ticket_info()`)
```python
Display Components:
├── Ticket metrics (ID, Location, Resolution Time, Status)
├── Original issue description
├── Processed description (if different)
├── Customer notification message
├── Additional ticket information
└── Download CSV functionality
```

#### Step 15: Create Download Export (`functions.py::create_download_button()`)
```python
CSV Export Contains:
├── All ticket details
├── Original and processed descriptions
├── Estimated resolution time
├── Customer notification
├── Timestamp
└── Processing method used
```

#### Step 16: Logging & Telemetry
```python
Application Insights Logging:
├── Ticket processing events
├── Search strategy success/failure
├── Performance metrics
├── Error tracking
└── User interaction patterns
```

---

### Phase 7: Error Handling & Cleanup

#### Step 17: Error Handling Strategies
```python
Error Categories:
├── Validation Errors → User-friendly messages
├── Service Unavailable → Graceful degradation
├── Authentication Failures → Configuration guidance
├── Network Issues → Retry logic where appropriate
└── Critical Errors → Error tickets with support info
```

#### Step 18: Resource Cleanup (`functions.py::cleanup_resources()`)
```python
On Application Shutdown:
├── Close Weaviate connections
├── Flush Redis connections
├── Close Azure Search clients
└── Flush Application Insights telemetry
```

---

## 🔍 Data Flow Diagram

```
User Input (Location + Description)
                    │
                    ▼
            Input Validation
                    │
                    ▼
              Cache Check ◄─────────────┐
                    │                  │
              Cache Miss               │
                    │                  │
                    ▼                  │
        Multi-Strategy Search          │
        ┌─────────────────────┐        │
        │ 1. Vector Active    │        │
        │ 2. Vector Historic  │        │
        │ 3. Hybrid Search    │        │
        │ 4. Text Search      │        │
        │ 5. Global Search    │        │
        │ 6. Invalid Response │        │
        └─────────────────────┘        │
                    │                  │
                    ▼                  │
         Calculate Resolution Time     │
                    │                  │
                    ▼                  │
           Create Ticket Data          │
                    │                  │
                    ▼                  │
        Generate AI Notification       │
                    │                  │
                    ▼                  │
         Store in Search & Vector      │
                    │                  │
                    ▼                  │
            Cache Result ──────────────┘
                    │
                    ▼
            Display Results
                    │
                    ▼
          Log Telemetry & Cleanup
```

---

## 🚦 Search Strategy Decision Tree

```
Start: New Ticket Request
│
├─ Has Active Vector Store?
│  ├─ YES → Search Active Vectors
│  │        ├─ Found Matches? → SUCCESS ✓
│  │        └─ No Matches → Continue
│  └─ NO → Continue
│
├─ Has Historic Vector Store?
│  ├─ YES → Search Historic Vectors  
│  │        ├─ Found Matches? → SUCCESS ✓
│  │        └─ No Matches → Continue
│  └─ NO → Continue
│
├─ Try Azure Hybrid Search
│  ├─ Has Embeddings? → Text + Vector Search
│  │        ├─ Found Matches? → SUCCESS ✓
│  │        └─ No Matches → Continue
│  └─ NO Embeddings → Text Only Search
│           ├─ Found Matches? → SUCCESS ✓
│           └─ No Matches → Continue
│
├─ Try Global Search (No Location Filter)
│  ├─ Found Matches? → SUCCESS ✓
│  └─ No Matches → Continue
│
└─ Return Invalid Query Response
   └─ Request More Details
```

---

## 🔧 Configuration Flow

```
Application Startup
│
├─ Load azure_auth.json
├─ Authenticate with Key Vault
├─ Retrieve Secrets:
│  ├─ AZURE-OPENAI-ENDPOINT
│  ├─ AZURE-SEARCH-ENDPOINT  
│  ├─ AZURE-SEARCH-ADMIN-KEY
│  ├─ WEAVIATE-URL (optional)
│  ├─ REDIS-URL (optional)
│  └─ APPLICATIONINSIGHTS-CONNECTION-STRING (optional)
│
├─ Test Connections:
│  ├─ Azure OpenAI → Create embeddings model
│  ├─ Azure Search → Test index access
│  ├─ Weaviate → Test collection access (optional)
│  └─ Redis → Test connection (optional)
│
└─ Initialize System Components
```

This comprehensive process flow shows exactly how your Smart Ticket Resolution Estimator works from startup to ticket resolution, including all fallback strategies, error handling, and data persistence mechanisms.