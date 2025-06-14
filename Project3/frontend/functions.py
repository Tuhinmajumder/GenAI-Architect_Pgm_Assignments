import csv
import logging
from io import StringIO
from typing import Optional, Tuple
import pandas as pd

import streamlit as st
from langchain_openai import AzureOpenAIEmbeddings
from azure.identity import DefaultAzureCredential
from authorization.authorization import retrive_credential

from backend.document_loader import TicketDataManager
from backend.vector_store import VectorStoreManager
from backend.rag_chain import TicketProcessor

from opencensus.ext.azure.log_exporter import AzureLogHandler


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler("ticket_system.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Configure Application Insights if connection string is available
if retrive_credential("APPLICATIONINSIGHTS-CONNECTION-STRING"):
    logger.addHandler(
        AzureLogHandler(
            connection_string=retrive_credential("APPLICATIONINSIGHTS-CONNECTION-STRING")
        )
    )

ACTIVE_INDEX = 'active-tickets'
HISTORIC_INDEX = 'historic-tickets'
ACTIVE_COLLECTION = 'Active_tickets'
HISTORIC_COLLECTION = 'Historic_tickets'
EMBEDDING_MODEL = "text-embedding-ada-002"

vector_stores = []

class AppInitializer:
    """
    Handles application initialization and setup with comprehensive error handling.
    
    This class manages the complete initialization workflow for the ticket processing
    system, including Azure OpenAI embeddings, ticket data loading from Azure Search,
    vector store setup, and ticket processor configuration. It provides robust error
    handling and graceful degradation when some services are unavailable.
    
    The initializer supports partial system functionality when not all components
    are available, allowing the application to work with Azure Search only if
    vector stores are unavailable.
    """
    
    @staticmethod
    def create_embeddings() -> Optional[AzureOpenAIEmbeddings]:
        """
        Create and configure Azure OpenAI embeddings model for vector generation.
        
        Sets up the Azure OpenAI text embedding service using Azure Active Directory
        authentication. The embeddings are used for generating vector representations
        of ticket descriptions for semantic search capabilities.
        
        Returns:
            Optional[AzureOpenAIEmbeddings]: Configured embeddings model if successful,
                                           None if Azure OpenAI is unavailable or
                                           configuration is missing.
                                           
        Raises:
            RuntimeError: If embeddings creation fails due to critical configuration
                         errors or authentication failures that cannot be recovered.
        """
        try:
            endpoint = retrive_credential("AZURE-OPENAI-ENDPOINT")
            if not endpoint:
                st.error("❌ AZURE_OPENAI_ENDPOINT not configured")
                return None
            
            credential = DefaultAzureCredential()
            token_provider = lambda: credential.get_token("https://cognitiveservices.azure.com/.default").token
            
            return AzureOpenAIEmbeddings(
                model=EMBEDDING_MODEL,
                azure_endpoint=endpoint,
                azure_deployment=EMBEDDING_MODEL,
                api_version="2024-06-01",
                azure_ad_token_provider=token_provider
            )
        
        except Exception as e:
            st.error(f"❌ Failed to initialize embeddings: {e}")
            logger.error(f"Embeddings initialization error: {e}")
            raise RuntimeError(f"Failed to create embeddings model: {e}")
    
    @staticmethod
    def load_ticket_data() -> Optional[Tuple]:
        """
        Load ticket data from Azure AI Search indexes containing blob storage data.
        
        Creates a TicketDataManager instance and loads both active and historic
        ticket documents from the configured Azure Search indexes. These indexes
        are populated by Azure Search indexers that process CSV files from blob storage.
        
        Returns:
            Optional[Tuple]: Tuple of (data_manager, active_docs, historic_docs) if
                           successful, None if data loading fails due to connectivity
                           issues or configuration problems.
                           
        Raises:
            RuntimeError: If ticket data loading fails due to critical Azure Search
                         connectivity issues, authentication failures, or data
                         processing errors that cannot be recovered.
        """
        try:
            data_manager = TicketDataManager(ACTIVE_INDEX, HISTORIC_INDEX)
            
            active_docs = data_manager.load_active_documents()
            historic_docs = data_manager.load_historic_documents()
            
            return data_manager, active_docs, historic_docs
        
        except Exception as e:
            st.error(f"❌ Failed to load ticket data: {e}")
            logger.error(f"Data loading error: {e}")
            raise RuntimeError(f"Failed to load ticket data from Azure Search: {e}")
    
    @staticmethod
    def setup_vector_stores(embeddings, active_docs, historic_docs) -> Optional[Tuple]:
        """
        Set up Weaviate vector stores with graceful degradation and error handling.
        
        Attempts to create and populate Weaviate vector stores for both active and
        historic tickets. Handles partial failures gracefully, allowing the system
        to continue with reduced functionality if some vector stores are unavailable.
        
        Args:
            embeddings: Azure OpenAI embeddings model for vector generation
            active_docs: List of active ticket documents to store
            historic_docs: List of historic ticket documents to store
            
        Returns:
            Optional[Tuple]: Tuple of (active_vsm, historic_vsm, active_collection,
                           historic_collection) where some elements may be None if
                           those specific vector stores are unavailable.
                           
        Raises:
            RuntimeError: If vector store setup fails completely and no fallback
                         options are available, or if critical errors occur during
                         document population that cannot be recovered.
        """
        global vector_stores
        
        try:
            st.info("🔄 Attempting to connect to Weaviate...")
            
            try:
                active_vsm = VectorStoreManager(ACTIVE_COLLECTION)
                st.success("✅ Connected to Weaviate for active tickets")
            except Exception as e:
                st.error(f"❌ Failed to connect to Weaviate for active tickets: {e}")
                st.warning("⚠️ Continuing with limited functionality (no vector search for active tickets)")
                active_vsm = None
            
            try:
                historic_vsm = VectorStoreManager(HISTORIC_COLLECTION)
                st.success("✅ Connected to Weaviate for historic tickets")
            except Exception as e:
                st.error(f"❌ Failed to connect to Weaviate for historic tickets: {e}")
                st.warning("⚠️ Continuing with limited functionality (no vector search for historic tickets)")
                historic_vsm = None
            
            if not active_vsm and not historic_vsm:
                st.warning("⚠️ Vector stores unavailable - using Azure AI Search only")
                return None, None, None, None
            
            if active_vsm:
                vector_stores.append(active_vsm)
            if historic_vsm:
                vector_stores.append(historic_vsm)
            
            active_collection = active_vsm.get_collection() if active_vsm else None
            historic_collection = historic_vsm.get_collection() if historic_vsm else None
            
            if active_vsm and active_collection and active_docs:
                try:
                    active_test = active_collection.aggregate.over_all(total_count=True)
                    if active_test.total_count == 0:
                        st.info(f"📤 Adding {len(active_docs)} active documents to vector store...")
                        active_vsm.add_documents(active_docs)
                        st.success(f"✅ Added {len(active_docs)} active documents to vector store")
                
                except Exception as e:
                    logger.warning(f"Could not check active collection counts: {e}")
                    try:
                        st.info("📤 Adding active documents to vector store...")
                        active_vsm.add_documents(active_docs)
                        st.success(f"✅ Added {len(active_docs)} active documents")
                    except Exception as add_error:
                        st.warning(f"⚠️ Could not add active documents: {add_error}")
            
            if historic_vsm and historic_collection and historic_docs:
                try:
                    historic_test = historic_collection.aggregate.over_all(total_count=True)
                    if historic_test.total_count == 0:
                        st.info(f"📤 Adding {len(historic_docs)} historic documents to vector store...")
                        historic_vsm.add_documents(historic_docs)
                        st.success(f"✅ Added {len(historic_docs)} historic documents to vector store")
                        
                except Exception as e:
                    logger.warning(f"Could not check historic collection counts: {e}")
                    try:
                        st.info("📤 Adding historic documents to vector store...")
                        historic_vsm.add_documents(historic_docs)
                        st.success(f"✅ Added {len(historic_docs)} historic documents")
                    except Exception as add_error:
                        st.warning(f"⚠️ Could not add historic documents: {add_error}")
            
            return active_vsm, historic_vsm, active_collection, historic_collection
        
        except Exception as e:
            st.error(f"❌ Failed to setup vector stores: {e}")
            logger.error(f"Vector store setup error: {e}")
            raise RuntimeError(f"Vector store setup failed: {e}")
    
    @staticmethod
    def initialize_system() -> Optional[Tuple]:
        """
        Initialize the complete RAG system with comprehensive error handling and progress tracking.
        
        Orchestrates the entire system initialization process including embeddings creation,
        data loading, vector store setup, and ticket processor configuration. Provides
        visual progress feedback and handles partial failures gracefully.
        
        Returns:
            Optional[Tuple]: Tuple of (data_manager, active_vsm, processor) if successful,
                           None if initialization fails due to critical errors that
                           prevent the system from functioning.
                           
        Raises:
            RuntimeError: If system initialization fails completely due to critical
                         configuration errors, service unavailability, or other
                         unrecoverable problems.
        """
        
        status_placeholder = st.empty()
        progress_bar = st.progress(0)
        
        try:
            status_placeholder.info("🧠 Creating embedding model...")
            progress_bar.progress(20)
            embeddings = AppInitializer.create_embeddings()
            if not embeddings:
                raise RuntimeError("Failed to create embeddings model")
            
            status_placeholder.info("📚 Loading ticket data from Azure AI Search...")
            progress_bar.progress(40)
            data_result = AppInitializer.load_ticket_data()
            if not data_result:
                raise RuntimeError("Failed to load ticket data")
            
            data_manager, active_docs, historic_docs = data_result
            
            status_placeholder.info("🔍 Setting up vector stores...")
            progress_bar.progress(60)
            vector_result = AppInitializer.setup_vector_stores(embeddings, active_docs, historic_docs)
            
            if vector_result is None:
                raise RuntimeError("Vector store setup failed completely")
            
            active_vsm, historic_vsm, active_collection, historic_collection = vector_result
            
            status_placeholder.info("🤖 Creating ticket processor...")
            progress_bar.progress(80)
            try:
                processor = TicketProcessor(
                    search_index=ACTIVE_INDEX,
                    active_vectorstore=active_vsm,
                    history_vectorstore=historic_vsm,
                    embedding_model=embeddings
                )
                
                progress_bar.progress(100)
                
                if active_vsm or historic_vsm:
                    status_placeholder.success("✅ RAG system initialized successfully!")
                else:
                    status_placeholder.warning("⚠️ System initialized with Azure Search only (limited vector capabilities)")
                
                import time
                time.sleep(2)
                status_placeholder.empty()
                progress_bar.empty()
                
                return data_manager, active_vsm, processor
            
            except Exception as e:
                st.error(f"❌ Failed to create ticket processor: {e}")
                logger.error(f"Ticket processor creation error: {e}")
                raise RuntimeError(f"Failed to create ticket processor: {e}")
                
        except Exception as e:
            status_placeholder.error(f"❌ System initialization failed: {e}")
            logger.error(f"System initialization error: {e}")
            raise RuntimeError(f"System initialization failed: {e}")

def cleanup_resources():
    """
    Clean up vector store connections and other resources on application shutdown.
    
    Ensures proper cleanup of Weaviate connections and other system resources
    to prevent connection leaks and ensure clean application termination.
    """
    global vector_stores
    for vsm in vector_stores:
        try:
            vsm.close()
        except Exception as e:
            logger.error(f"Error during cleanup: {e}")
    logger.info("Cleanup completed")

def validate_environment():
    """
    Validate that all required environment variables are properly configured.
    
    Checks for the presence of essential environment variables needed for
    system operation and provides helpful feedback about missing or optional
    configuration items.
    
    Returns:
        bool: True if all required variables are present, False if critical
              configuration is missing that would prevent system operation.
    """
    required_vars = [
        "AZURE-OPENAI-ENDPOINT",
        "AZURE_SEARCH-ENDPOINT",
        "AZURE-SEARCH-ADMIN-KEY"
    ]
    
    optional_vars = [
        "WEAVIATE-URL",
        "REDIS-URL",
        "AZURE-STORAGE-ACCOUNT-NAME",
        "AZURE-STORAGE-CONTAINER-NAME",
        "APPLICATIONINSIGHTS-CONNECTION-STRING"
    ]
    
    missing_vars = []
    for var in required_vars:
        if not retrive_credential(var):
            missing_vars.append(var)
    
    if missing_vars:
        st.error(f"❌ Missing required environment variables: {', '.join(missing_vars)}")
        st.info("Please check your .env file and ensure all required variables are set.")
        return False
    
    missing_optional = [var for var in optional_vars if not retrive_credential(var)]
    if missing_optional:
        st.info(f"ℹ️ Optional variables not set: {', '.join(missing_optional)} - some features may be limited")
    
    return True

def display_ticket_form() -> Tuple[Optional[int], Optional[str]]:
    """
    Display the ticket submission form with location selection and description input.
    
    Creates an intuitive form interface for users to submit new tickets with
    location selection and detailed issue description. Provides helpful guidance
    and validation messaging to ensure quality ticket submissions.
    
    Returns:
        Tuple[Optional[int], Optional[str]]: Tuple of (locationID, description)
                                           if form is submitted, (None, None) otherwise.
    """
    st.markdown("### 🎫 Submit a New Ticket")
    
    with st.form("ticket_form", clear_on_submit=False):
        col1, col2 = st.columns([1, 2])
        
        with col1:
            st.markdown("**Location ID:**")
            location_options = list(range(1, 40))
            locationID = st.selectbox(
                "Select your location",
                options=location_options,
                index=None,
                placeholder="Choose location...",
                label_visibility="collapsed"
            )
        
        st.markdown("**Issue Description:**")
        description = st.text_area(
            "Describe your technical issue in detail",
            placeholder="Please provide detailed information about your technical issue...\n\nExample:\n- What were you trying to do?\n- What happened instead?\n- Any error messages you saw?\n- When did this start happening?",
            height=120,
            label_visibility="collapsed"
        )
        
        st.markdown("💡 *Tip: The more details you provide, the better we can estimate resolution time.*")
        
        submitted = st.form_submit_button(
            "🚀 Submit Ticket", 
            use_container_width=True,
            type="primary"
        )
        
        if submitted:
            return locationID, description
    
    return None, None

def process_and_display_ticket(processor: TicketProcessor, active_vsm: VectorStoreManager, 
                             locationID: int, description: str):
    """
    Process a ticket request and display comprehensive results to the user.
    
    Handles the complete ticket processing workflow including validation, processing
    through the RAG system, storage in search indexes and vector stores, and
    presentation of results with detailed ticket information and notifications.
    
    Args:
        processor (TicketProcessor): Configured ticket processor for handling requests
        active_vsm (VectorStoreManager): Vector store manager for active tickets
        locationID (int): Location identifier for the ticket
        description (str): Detailed description of the technical issue
        
    Raises:
        RuntimeError: If ticket processing fails due to system errors, though
                     the method attempts to display user-friendly error messages
                     rather than raising exceptions when possible.
    """
    try:
        with st.spinner("🔄 Processing your ticket..."):
            ticket_type, ticket_data, notification = processor.process_ticket_request(description, locationID)
            
            if ticket_data.get("is_valid", True):
                try:
                    processor.add_ticket_to_search(ticket_data)
                    if active_vsm:
                        active_vsm.add_single_document(ticket_data)
                except Exception as e:
                    logger.warning(f"Failed to add ticket to stores: {e}")
                    st.warning("⚠️ Ticket processed but may not be saved to all systems.")
        
        if ticket_type == "invalid_query":
            st.warning("⚠️ Please provide more specific details about your issue.")
        elif ticket_type == "error":
            st.error("❌ There was an error processing your ticket. Please try again.")
        else:
            st.success("✅ Ticket processed successfully!")
        
        display_ticket_info(ticket_data, description, notification, ticket_type)
        
    except ValueError as e:
        st.error(f"❌ Input Error: {e}")
        raise RuntimeError(f"Ticket validation failed: {e}")
    except Exception as e:
        st.error(f"❌ Processing Error: {e}")
        logger.error(f"Ticket processing error: {e}")
        raise RuntimeError(f"Ticket processing failed: {e}")

def display_ticket_info(ticket_data: dict, original_description: str, notification: str, ticket_type: str):
    """
    Display comprehensive ticket information in a well-formatted, user-friendly layout.
    
    Creates a detailed presentation of the processed ticket including metrics,
    descriptions, notifications, and additional information. Provides download
    functionality for record keeping and follow-up purposes. Logs ticket information
    to a file and Application Insights for auditing and monitoring.
    
    Args:
        ticket_data (dict): Complete ticket information including ID, location, times, etc.
        original_description (str): User's original issue description
        notification (str): Generated customer service notification message
        ticket_type (str): Classification of ticket processing result for status display
    """
    
    # Log ticket information
    resolution_time = ticket_data['estimated_resolution_time']
    status_map = {
        "new_active_ticket": "Active",
        "new_historic_ticket": "Historic",
        "new_azure_search_ticket": "Azure",
        "invalid_query": "Invalid",
        "error": "Error"
    }
    status = status_map.get(ticket_type, "Processed")
    
    ticket_info = {
        "TicketID": ticket_data["TicketID"],
        "LocationID": ticket_data["locationID"],
        "EstimatedResolutionTime": f"{resolution_time}h" if resolution_time > 0 else "TBD",
        "Status": status,
        "OriginalDescription": original_description,
        "ProcessedDescription": ticket_data.get("description", ""),
        "CustomerNotification": notification,
        "TicketType": ticket_data.get("type", "complaint").title(),
        "ClusterID": ticket_data.get("clusterID", "N/A"),
        "CustomerID": ticket_data.get("customerID", "N/A"),
        "ProcessingMethod": ticket_type.replace("_", " ").title(),
        "Timestamp": pd.Timestamp.now().strftime("%Y-%m-%d %H:%M:%S")
    }
    
    logger.info(
        "Ticket Information Displayed",
        extra={
            "custom_dimensions": ticket_info
        }
    )
    
    st.markdown("---")
    st.markdown("### 📋 Ticket Information")
    
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        st.metric("🎫 Ticket ID", ticket_data["TicketID"])
    
    with col2:
        st.metric("📍 Location", ticket_data["locationID"])
    
    with col3:
        if resolution_time > 0:
            st.metric("⏱️ Est. Resolution", f"{resolution_time}h")
        else:
            st.metric("⏱️ Est. Resolution", "TBD")
    
    with col4:
        st.metric("📊 Status", status)
    
    st.markdown("### 📝 Issue Details")
    
    with st.expander("🔍 Original Description", expanded=True):
        st.text_area(
            "Original issue description",
            value=original_description, 
            height=100, 
            disabled=True, 
            label_visibility="collapsed"
        )
    
    if ticket_data["description"] != original_description and ticket_data["description"]:
        with st.expander("🔧 Processed Description", expanded=False):
            st.text_area(
                "AI-processed description",
                value=ticket_data["description"], 
                height=80, 
                disabled=True, 
                label_visibility="collapsed"
            )
    
    st.markdown("### 📢 Customer Notification")
    st.info(notification)
    
    if ticket_data.get("is_valid", True) and resolution_time > 0:
        st.markdown("### ℹ️ Additional Information")
        
        info_col1, info_col2 = st.columns(2)
        
        with info_col1:
            st.markdown(f"**Ticket Type:** {ticket_data.get('type', 'complaint').title()}")
            st.markdown(f"**Cluster ID:** {ticket_data.get('clusterID', 'N/A')}")
        
        with info_col2:
            st.markdown(f"**Customer ID:** {ticket_data.get('customerID', 'N/A')}")
            st.markdown(f"**Processing Method:** {ticket_type.replace('_', ' ').title()}")
    
    create_download_button(ticket_data, original_description, notification)

def create_download_button(ticket_data: dict, original_description: str, notification: str):
    """
    Create a download button for exporting ticket details as CSV for record keeping.
    
    Generates a formatted CSV file containing all ticket information including
    original and processed descriptions, estimated resolution time, and customer
    notification message with timestamp for audit trail purposes.
    
    Args:
        ticket_data (dict): Complete ticket information to include in export
        original_description (str): User's original issue description
        notification (str): Generated customer notification message
    """
    
    st.markdown("### 💾 Download Ticket Details")
    
    output = StringIO()
    writer = csv.writer(output, quoting=csv.QUOTE_ALL)
    
    writer.writerow([
        "Ticket ID", 
        "Location ID", 
        "Customer ID",
        "Original Description", 
        "Processed Description",
        "Estimated Resolution (hours)", 
        "Ticket Type",
        "Customer Notification",
        "Created At"
    ])
    
    writer.writerow([
        ticket_data["TicketID"],
        ticket_data["locationID"],
        ticket_data.get("customerID", "N/A"),
        original_description,
        ticket_data.get("description", ""),
        ticket_data["estimated_resolution_time"],
        ticket_data.get("type", "complaint"),
        notification,
        pd.Timestamp.now().strftime("%Y-%m-%d %H:%M:%S")
    ])
    
    csv_content = output.getvalue()
    output.close()
    
    st.download_button(
        label="📥 Download Ticket Details (CSV)",
        data=csv_content,
        file_name=f"ticket_{ticket_data['TicketID']}_details.csv",
        mime="text/csv",
        use_container_width=True
    )

def display_sidebar_info():
    """
    Display comprehensive sidebar information including usage instructions and diagnostic tools.
    
    Creates an informative sidebar with user guidance, system feature descriptions,
    status indicators, and diagnostic tools for troubleshooting and system validation.
    Provides quick access to system testing and configuration validation tools.
    """
    
    st.sidebar.markdown("### 📋 How to Use")
    st.sidebar.markdown("""
    1. **Select Location**: Choose your location ID from dropdown
    2. **Describe Issue**: Provide detailed technical problem description  
    3. **Submit Ticket**: Click submit to process your request
    4. **Review Results**: Check estimated resolution time and notification
    5. **Download**: Save ticket details for your records
    """)
    
    st.sidebar.markdown("### 💡 Tips for Better Results")
    st.sidebar.markdown("""
    - **Be Specific**: Include error messages, steps to reproduce
    - **Add Context**: When did it start? What changed?
    - **Include Impact**: How many users affected?
    - **Mention Urgency**: Is this blocking critical work?
    """)
    
    st.sidebar.markdown("### ⚙️ System Features")
    st.sidebar.markdown("""
    - **🤖 AI-Powered**: Uses machine learning for smart estimation
    - **📊 Historical Data**: Learns from past similar tickets
    - **⚡ Real-time**: Instant processing and response
    - **💾 Cached**: Faster responses for common issues
    - **🔍 Multi-Search**: Multiple search strategies
    - **☁️ Azure Integration**: Uses Azure AI Search with blob storage indexing
    """)
    
    st.sidebar.markdown("---")
    if st.session_state.get("system_ready", False):
        st.sidebar.success("✅ System Status: Online")
        st.sidebar.markdown("All services are operational")
    else:
        st.sidebar.error("❌ System Status: Offline")
        st.sidebar.markdown("System is initializing or offline")
    
    st.sidebar.markdown("---")