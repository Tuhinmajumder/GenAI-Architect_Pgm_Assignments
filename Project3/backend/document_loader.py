import pandas as pd
from typing import List, Dict, Any
from langchain_core.documents import Document
from langchain_core.prompts import PromptTemplate
from langchain_openai import AzureChatOpenAI
from azure.search.documents import SearchClient
from azure.core.credentials import AzureKeyCredential
from azure.identity import DefaultAzureCredential
import logging
from authorization.authorization import retrive_credential

# load_dotenv()
logger = logging.getLogger(__name__)


class DocumentLoader:
    """
    Loads and processes ticket data from Azure AI Search (which indexes blob storage CSV files).
    
    This class handles the extraction of support ticket data from Azure AI Search indexes that
    contain CSV data from blob storage. It automatically detects field names, maps them to
    standardized formats, and converts the data into Document objects suitable for AI processing.
    
    The class supports both active tickets (currently open) and historic tickets (resolved),
    with different field mappings and processing logic for each type.
    
    Attributes:
        search_index_name (str): Name of the Azure AI Search index to query
        ticket_type (str): Type of tickets - either "active" or "historic"
        search_client (SearchClient): Azure Search client for querying the index
        summarization_chain: Optional AI chain for summarizing long text descriptions
    """
    
    def __init__(self, search_index_name: str, ticket_type: str = "active"):
        """
        Initialize the DocumentLoader with Azure AI Search index configuration.
        
        Sets up connections to Azure AI Search and optionally configures AI-powered text
        summarization for processing long ticket descriptions.
        
        Args:
            search_index_name (str): Name of the Azure AI Search index that contains the ticket data
            ticket_type (str, optional): Type of tickets to process. Must be either "active" 
                                       for open tickets or "historic" for resolved tickets. 
                                       Defaults to "active".
        """
        self.search_index_name = search_index_name
        self.ticket_type = ticket_type
        self.search_client = self._create_search_client(search_index_name)
        self.summarization_chain = self._create_summarization_chain()
    
    def _create_search_client(self, index_name: str) -> SearchClient:
        """
        Create and configure an Azure AI Search client.
        
        Establishes a connection to Azure AI Search using credentials from environment
        variables. The client is used to query the specified search index for ticket data.
        
        Args:
            index_name (str): Name of the search index to connect to
            
        Returns:
            SearchClient: Configured Azure Search client instance
            
        Raises:
            RuntimeError: If the search client cannot be created due to missing credentials
                         or connection issues
        """
        try:
            endpoint = retrive_credential("AZURE-SEARCH-ENDPOINT")
            admin_key = retrive_credential("AZURE-SEARCH-ADMIN-KEY")
            
            return SearchClient(
                endpoint=endpoint,
                index_name=index_name,
                credential=AzureKeyCredential(admin_key)
            )
        except Exception as e:
            raise RuntimeError(f"Failed to create search client for index {index_name}: {e}")
    
    def _create_summarization_chain(self):
        """
        Create an AI-powered text summarization chain for processing long ticket descriptions.
        
        Sets up an Azure OpenAI-based summarization system that can condense lengthy ticket
        descriptions while preserving important technical details. If Azure OpenAI is not
        available or configured, the system will fall back to simple text truncation.
        
        Returns:
            Optional[Any]: Configured summarization chain if successful, None if unavailable
                          or if setup fails. When None, the system will use text truncation
                          as a fallback for long descriptions.
        """
        try:
            endpoint = retrive_credential("AZURE-OPENAI-ENDPOINT")
            if not endpoint:
                logger.warning("AZURE_OPENAI_ENDPOINT not available - summarization disabled")
                return None
            
            prompt = PromptTemplate.from_template(
                "Summarize this ticket description concisely while preserving key technical details:\n{text}\n\nSUMMARY:"
            )
            
            credential = DefaultAzureCredential()
            token_provider = lambda: credential.get_token("https://cognitiveservices.azure.com/.default").token
            
            llm = AzureChatOpenAI(
                model="gpt-4o-mini",
                azure_endpoint=endpoint,
                azure_deployment="gpt-4o-mini",
                api_version="2024-12-01-preview",
                azure_ad_token_provider=token_provider,
                temperature=0
            )
            
            return prompt | llm
        except Exception as e:
            logger.warning(f"Failed to create summarization chain: {e}")
            return None
    
    def _detect_field_names(self, sample_result: Dict) -> Dict[str, str]:
        """
        Automatically detect and map CSV field names to standardized internal field names.
        
        Different CSV files may use varying column names for the same data (e.g., "TicketID" vs 
        "ticket_id" vs "id"). This method analyzes a sample record to identify which actual
        field names correspond to the required data fields, creating a mapping dictionary
        for consistent data extraction.
        
        The method handles both exact matches and partial matches (case-insensitive) to
        accommodate various naming conventions used in different data sources.
        
        Args:
            sample_result (Dict): A sample record from the search results used to analyze
                                available field names and their structure
                                
        Returns:
            Dict[str, str]: Mapping dictionary where keys are standardized field names
                           (TicketID, locationID, description, customer_id, resolution_time)
                           and values are the actual field names found in the data
                           
        Raises:
            RuntimeError: If field name detection fails due to invalid data structure
                         or other processing errors
        """
        try:
            mappings = {}
            available_keys = list(sample_result.keys())
            
            logger.debug(f"Available fields in {self.search_index_name}: {available_keys}")
            
            field_variations = {
                'TicketID': ['TicketID', 'ticket_id', 'ticketId', 'id', 'ID'],
                'locationID': ['locationID', 'location_id', 'locationId', 'location'],
                'description': ['description', 'Description', 'desc', 'content', 'text'],
                'customer_id': ['customerID', 'customer_id', 'customerId', 'customer']
            }
            
            if self.ticket_type == "active":
                field_variations['resolution_time'] = ['estimated_resolution_time', 'estimatedResolutionTime', 'estimation_time', 'eta', 'est_resolution_time']
            else:
                field_variations['resolution_time'] = ['actual_resolution_time', 'actualResolutionTime', 'resolution_time', 'actual_time', 'resolved_time']
            
            for standard_name, variations in field_variations.items():
                for variation in variations:
                    if variation in available_keys:
                        mappings[standard_name] = variation
                        break
                
                if standard_name not in mappings:
                    for key in available_keys:
                        if any(var.lower() in key.lower() for var in variations):
                            mappings[standard_name] = key
                            break
            
            logger.debug(f"Field mappings for {self.search_index_name}: {mappings}")
            return mappings
        except Exception as e:
            raise RuntimeError(f"Failed to detect field names in search results: {e}")
    
    def load_tickets(self) -> pd.DataFrame:
        """
        Load all ticket records from the Azure AI Search index and convert to a DataFrame.
        
        Retrieves all available ticket records from the search index, automatically detects
        the field structure, and converts the data into a standardized pandas DataFrame format.
        The method handles field name mapping, data type conversion, and basic data validation.
        
        For large datasets, the method processes records in batches and provides progress
        logging. Only records with essential data (TicketID and description) are included
        in the final DataFrame.
        
        Returns:
            pd.DataFrame: DataFrame containing all ticket records with standardized column names:
                         - TicketID: Unique identifier for the ticket
                         - locationID: Location or site identifier  
                         - description: Ticket description/content
                         - customerID: Customer identifier (if available)
                         - estimated_resolution_time: ETA for active tickets
                         - actual_resolution_time: Completion time for historic tickets
                         
        Raises:
            RuntimeError: If the search operation fails, if no valid tickets are found,
                         or if there are issues with data processing or field mapping
        """
        try:
            results = self.search_client.search(
                search_text="*", 
                top=10000,
                include_total_count=True
            )
            
            tickets = []
            field_mappings = {}
            first_result = True
            
            logger.info(f"Loading tickets from Azure AI Search index: {self.search_index_name}")
            
            for result in results:
                if first_result and result:
                    field_mappings = self._detect_field_names(result)
                    first_result = False
                
                ticket_data = {
                    "TicketID": self._safe_get(result, 'TicketID', field_mappings),
                    "locationID": self._safe_get(result, 'locationID', field_mappings),
                    "description": self._safe_get(result, 'description', field_mappings)
                }
                
                customer_id = self._safe_get(result, 'customer_id', field_mappings)
                if customer_id:
                    ticket_data["customerID"] = customer_id
                
                resolution_time = self._safe_get(result, 'resolution_time', field_mappings)
                if self.ticket_type == "active":
                    ticket_data["estimated_resolution_time"] = resolution_time
                else:
                    ticket_data["actual_resolution_time"] = resolution_time
                
                if ticket_data["TicketID"] and ticket_data["description"]:
                    tickets.append(ticket_data)
            
            logger.info(f"Successfully loaded {len(tickets)} tickets from {self.search_index_name}")
            
            if len(tickets) == 0:
                logger.warning(f"No tickets found in search index {self.search_index_name}!")
                logger.warning("Make sure your Azure AI Search indexer has successfully indexed the blob storage CSV files.")
                
            return pd.DataFrame(tickets)
            
        except Exception as e:
            logger.error(f"Error loading tickets from {self.search_index_name}: {str(e)}")
            raise RuntimeError(f"Failed to load tickets from search index: {e}")
    
    def _safe_get(self, result: Dict, field_key: str, field_mappings: Dict) -> Any:
        """
        Safely extract field values from search results using the detected field mappings.
        
        Uses the field mapping dictionary to translate between standardized field names and
        the actual field names present in the data. Includes fallback logic to handle cases
        where field mapping detection may have missed certain fields.
        
        Args:
            result (Dict): Individual search result record containing the raw data
            field_key (str): Standardized field name to extract (e.g., 'TicketID', 'description')
            field_mappings (Dict): Mapping from standardized names to actual field names
            
        Returns:
            Any: The field value if found, empty string if the field is missing or None
            
        Raises:
            RuntimeError: If field extraction fails due to data structure issues or
                         unexpected errors during value retrieval
        """
        try:
            if field_key in field_mappings:
                actual_field = field_mappings[field_key]
                value = result.get(actual_field)
                return value if value is not None else ""
            else:
                fallback_mapping = {
                    'TicketID': 'TicketID',
                    'locationID': 'locationID',
                    'description': 'description',
                    'customer_id': 'customerID',
                    'resolution_time': 'estimated_resolution_time' if self.ticket_type == "active" else 'actual_resolution_time'
                }
                fallback_field = fallback_mapping.get(field_key, field_key)
                return result.get(fallback_field, "")
        except Exception as e:
            raise RuntimeError(f"Failed to extract field {field_key} from search result: {e}")
    
    def summarize_if_long(self, text: str, max_length: int = 1500) -> str:
        """
        Process and potentially shorten long text descriptions using AI summarization or truncation.
        
        For ticket descriptions that exceed the specified maximum length, this method attempts
        to create a concise summary using AI while preserving important technical details.
        If AI summarization is unavailable, it falls back to simple text truncation.
        
        The method handles various text input types and validates content before processing.
        Short descriptions that are already within the length limit are returned unchanged.
        
        Args:
            text (str): The original text content to process (typically ticket description)
            max_length (int, optional): Maximum allowed text length in characters. 
                                      Defaults to 1500 characters.
                                      
        Returns:
            str: Processed text that is either:
                - Original text (if already short enough)
                - AI-generated summary (if summarization is available)
                - Truncated text with ellipsis (fallback option)
                - Empty string (if input is invalid or empty)
                
        Raises:
            RuntimeError: If text processing fails due to unexpected errors in validation
                         or processing logic (note: AI summarization failures are handled
                         gracefully with fallback to truncation)
        """
        try:
            if not isinstance(text, str) or not text.strip():
                return ""
            
            if len(text) <= max_length:
                return text
            
            if not self.summarization_chain:
                logger.debug("Summarization not available, truncating text")
                return text[:1000] + "..."
            
            try:
                summary = self.summarization_chain.invoke({"text": text})
                return summary.content.strip() if hasattr(summary, 'content') else str(summary).strip()
            except Exception as e:
                logger.warning(f"Summarization failed: {e}")
                return text[:1000] + "..."
        except Exception as e:
            raise RuntimeError(f"Failed to process text for summarization: {e}")
    
    def create_documents(self, df: pd.DataFrame) -> List[Document]:
        """
        Convert a pandas DataFrame of ticket data into Document objects for AI processing.
        
        Transforms structured ticket data into Document objects that can be used with
        LangChain and other AI frameworks. Each ticket becomes a Document with the
        (potentially summarized) description as content and all other ticket information
        stored as metadata.
        
        The method filters out tickets with insufficient description content and processes
        long descriptions through summarization. All metadata fields are converted to
        strings for consistency.
        
        Args:
            df (pd.DataFrame): DataFrame containing ticket data with standardized column names
                              (TicketID, locationID, description, etc.)
                              
        Returns:
            List[Document]: List of Document objects where each contains:
                           - page_content: The ticket description (potentially summarized)
                           - metadata: Dictionary with ticket information including:
                             * TicketID: Unique ticket identifier
                             * locationID: Location/site identifier
                             * ticket_type: "active" or "historic"
                             * customer_id: Customer identifier (if available)
                             * estimated_resolution_time: ETA (for active tickets)
                             * actual_resolution_time: Completion time (for historic tickets)
                             
        Raises:
            RuntimeError: If document creation fails due to DataFrame processing errors,
                         metadata creation issues, or Document object instantiation problems
        """
        try:
            documents = []
            
            for _, row in df.iterrows():
                description = self.summarize_if_long(str(row.get('description', '')))
                
                if not description or len(description.strip()) < 10:
                    continue
                
                metadata = {
                    'TicketID': str(row.get('TicketID', '')),
                    'locationID': str(row.get('locationID', '')),
                    'ticket_type': self.ticket_type
                }
                
                if 'customerID' in row and row['customerID']:
                    metadata['customer_id'] = str(row['customerID'])
                
                if self.ticket_type == "active":
                    resolution_time = row.get('estimated_resolution_time', '')
                    if resolution_time:
                        metadata['estimated_resolution_time'] = str(resolution_time)
                else:
                    resolution_time = row.get('actual_resolution_time', '')
                    if resolution_time:
                        metadata['actual_resolution_time'] = str(resolution_time)
                
                doc = Document(
                    page_content=description,
                    metadata=metadata
                )
                documents.append(doc)
            
            logger.info(f"Created {len(documents)} document objects from {len(df)} tickets")
            return documents
        except Exception as e:
            raise RuntimeError(f"Failed to create documents from DataFrame: {e}")
    
    def load_documents(self) -> List[Document]:
        """
        Complete workflow to load tickets from Azure Search and convert them to Document objects.
        
        This is the main method that combines the entire data loading and processing pipeline:
        1. Loads raw ticket data from Azure AI Search index
        2. Converts to standardized DataFrame format
        3. Processes and creates Document objects for AI use
        
        This method provides the most convenient interface for getting ready-to-use Document
        objects from the ticket data source.
        
        Returns:
            List[Document]: List of Document objects ready for use with AI/ML frameworks,
                           where each Document contains a ticket description and comprehensive
                           metadata about the ticket
                           
        Raises:
            RuntimeError: If any step in the loading pipeline fails, including Azure Search
                         connectivity issues, data processing errors, or Document creation problems
        """
        try:
            tickets_df = self.load_tickets()
            return self.create_documents(tickets_df)
        except Exception as e:
            raise RuntimeError(f"Failed to load documents for {self.ticket_type} tickets: {e}")


class TicketDataManager:
    """
    High-level manager for handling both active and historic ticket data from Azure AI Search.
    
    This class provides a unified interface for working with two different types of support
    tickets stored in separate Azure AI Search indexes. It manages the complexity of dealing
    with different data structures and processing requirements for active vs. historic tickets.
    
    The manager handles both types of tickets:
    - Active tickets: Currently open tickets with estimated resolution times
    - Historic tickets: Completed/resolved tickets with actual resolution times
    
    This abstraction allows applications to easily work with both ticket types through a
    single, consistent interface while maintaining the flexibility to access each type
    independently when needed.
    
    Attributes:
        active_loader (DocumentLoader): Loader configured for active ticket data
        historic_loader (DocumentLoader): Loader configured for historic ticket data
    """
    
    def __init__(self, active_index: str, historic_index: str):
        """
        Initialize the TicketDataManager with Azure AI Search index configurations.
        
        Sets up two separate DocumentLoader instances, one for each ticket type, with
        the appropriate configurations for handling active vs. historic ticket data.
        
        Args:
            active_index (str): Name of the Azure AI Search index containing active ticket data
            historic_index (str): Name of the Azure AI Search index containing historic ticket data
        """
        self.active_loader = DocumentLoader(active_index, "active")
        self.historic_loader = DocumentLoader(historic_index, "historic")
    
    def load_active_documents(self) -> List[Document]:
        """
        Load and process active ticket data into Document objects.
        
        Retrieves all active (currently open) tickets from the configured Azure Search index
        and converts them into Document objects suitable for AI processing. Active tickets
        include estimated resolution times and current status information.
        
        Returns:
            List[Document]: List of Document objects for active tickets, where each contains
                           the ticket description as content and ticket metadata including
                           estimated resolution times
                           
        Raises:
            RuntimeError: If loading active tickets fails due to connectivity issues,
                         data processing errors, or configuration problems with the
                         active tickets search index
        """
        try:
            return self.active_loader.load_documents()
        except Exception as e:
            logger.error(f"Failed to load active documents: {e}")
            raise RuntimeError(f"Failed to load active documents: {e}")
    
    def load_historic_documents(self) -> List[Document]:
        """
        Load and process historic ticket data into Document objects.
        
        Retrieves all historic (resolved/completed) tickets from the configured Azure Search
        index and converts them into Document objects. Historic tickets include actual
        resolution times and completion status information.
        
        Returns:
            List[Document]: List of Document objects for historic tickets, where each contains
                           the ticket description as content and ticket metadata including
                           actual resolution times and completion information
                           
        Raises:
            RuntimeError: If loading historic tickets fails due to connectivity issues,
                         data processing errors, or configuration problems with the
                         historic tickets search index
        """
        try:
            return self.historic_loader.load_documents()
        except Exception as e:
            logger.error(f"Failed to load historic documents: {e}")
            raise RuntimeError(f"Failed to load historic documents: {e}")
    
    def load_all_documents(self) -> tuple[List[Document], List[Document]]:
        """
        Load both active and historic ticket documents in a single operation.
        
        Convenience method that loads both types of tickets simultaneously, providing
        a complete view of all ticket data across both indexes. This is useful for
        applications that need to analyze or process both active and historic tickets together.
        
        Returns:
            tuple[List[Document], List[Document]]: A tuple containing two lists:
                - First element: List of active ticket Document objects
                - Second element: List of historic ticket Document objects
                
        Raises:
            RuntimeError: If loading either type of tickets fails. The error will indicate
                         which specific ticket type(s) caused the failure, allowing for
                         targeted troubleshooting
        """
        try:
            return self.load_active_documents(), self.load_historic_documents()
        except Exception as e:
            raise RuntimeError(f"Failed to load all documents: {e}")