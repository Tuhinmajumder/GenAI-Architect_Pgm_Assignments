import logging
from typing import List, Dict, Any, Optional
import weaviate
from weaviate.auth import AuthApiKey
from langchain_core.documents import Document
from langchain_openai import AzureOpenAIEmbeddings
from azure.identity import DefaultAzureCredential
from weaviate.classes.query import MetadataQuery, Filter
from weaviate.classes.init import AdditionalConfig, Timeout
from weaviate.classes.config import Property, DataType
from authorization.authorization import retrive_credential

logger = logging.getLogger(__name__)


class VectorStoreManager:
    """
    Manages Weaviate vector store operations for document similarity search and storage.
    
    This class provides a comprehensive interface for working with Weaviate vector databases,
    specifically designed for storing and searching support ticket documents. It handles
    the complete lifecycle of vector operations including connection management, collection
    creation, document embedding, storage, and similarity search.
    
    The manager supports both active and historic ticket collections with different schema
    configurations, automatic embedding generation using Azure OpenAI, and advanced search
    capabilities with location-based filtering.
    
    Key features:
    - Automatic connection management with proper authentication
    - Dynamic collection creation with appropriate schemas
    - Batch document processing for efficient storage
    - Similarity search with configurable filters
    - Robust error handling and connection management
    
    Attributes:
        collection_name (str): Name of the Weaviate collection to work with
        embedding_model (AzureOpenAIEmbeddings): Azure OpenAI model for generating embeddings
        client (weaviate.WeaviateClient): Connected Weaviate client instance
    """
    
    def __init__(self, collection_name: str):
        """
        Initialize the VectorStoreManager with a specific collection configuration.
        
        Sets up the complete vector store infrastructure including Azure OpenAI embeddings,
        Weaviate client connection, and ensures the target collection exists with the
        appropriate schema for the ticket type.
        
        Args:
            collection_name (str): Name of the Weaviate collection to create or use.
                                 Should indicate ticket type (e.g., "active_tickets", 
                                 "historic_tickets") as this affects the schema configuration
                                 and which resolution time fields are included.
        """
        self.collection_name = collection_name
        self.embedding_model = self._create_embeddings()
        self.client = self._create_weaviate_client()
        self._ensure_collection_exists()
    
    def _create_embeddings(self) -> AzureOpenAIEmbeddings:
        """
        Create and configure Azure OpenAI embeddings model for vector generation.
        
        Sets up the Azure OpenAI embeddings service using Azure Active Directory authentication
        to generate high-quality vector representations of ticket descriptions. The embeddings
        are used for similarity search and document retrieval operations.
        
        Returns:
            AzureOpenAIEmbeddings: Configured Azure OpenAI embeddings model using the
                                  text-embedding-ada-002 model for generating 1536-dimensional
                                  vectors from text content.
                                  
        Raises:
            RuntimeError: If the embeddings model cannot be created due to missing Azure
                         OpenAI endpoint configuration, authentication failures, or service
                         connectivity issues.
        """
        try:
            endpoint = retrive_credential("AZURE-OPENAI-ENDPOINT")
            
            credential = DefaultAzureCredential()
            token_provider = lambda: credential.get_token("https://cognitiveservices.azure.com/.default").token
            
            return AzureOpenAIEmbeddings(
                model="text-embedding-ada-002",
                azure_endpoint=endpoint,
                azure_deployment="text-embedding-ada-002",
                azure_ad_token_provider=token_provider
            )
        except Exception as e:
            raise RuntimeError(f"Failed to create embeddings model: {e}")
    
    def _create_weaviate_client(self) -> weaviate.WeaviateClient:
        """
        Create and configure Weaviate client connection with proper authentication and timeouts.
        
        Establishes a connection to Weaviate Cloud using the provided URL and API key,
        configures appropriate timeouts for different operations, and validates the
        connection by testing basic operations.
        
        Returns:
            weaviate.WeaviateClient: Connected and validated Weaviate client instance
                                   ready for database operations with configured timeouts
                                   and authentication.
                                   
        Raises:
            RuntimeError: If the Weaviate connection cannot be established due to invalid
                         URL format, authentication failures, network connectivity issues,
                         or service unavailability.
        """
        try:
            url = retrive_credential("WEAVIATE-URL")
            api_key = retrive_credential("WEAVIATE-API-KEY")
            
            if not url.startswith(("http://", "https://")):
                url = f"https://{url}"
            
            auth_config = AuthApiKey(api_key=api_key) if api_key else None
            
            additional_config = AdditionalConfig(
                timeout=Timeout(init=60, query=30, insert=30)
            )
            
            logger.info("Connecting to Weaviate...")
            client = weaviate.connect_to_weaviate_cloud(
                cluster_url=url,
                auth_credentials=auth_config,
                additional_config=additional_config
            )
            
            client.collections.list_all()
            logger.info("Successfully connected to Weaviate")
            return client
        except Exception as e:
            logger.error(f"Failed to connect to Weaviate: {e}")
            raise RuntimeError(f"Could not connect to Weaviate: {e}")
    
    def _ensure_collection_exists(self):
        """
        Create the target collection if it doesn't exist with appropriate schema configuration.
        
        Checks if the specified collection exists in the Weaviate instance and creates it
        if necessary. The schema is automatically configured based on the collection name,
        with different properties for active vs. historic ticket collections.
        
        For active ticket collections, includes 'estimated_resolution_time' property.
        For historic ticket collections, includes 'actual_resolution_time' property.
        All collections include standard properties: TicketID, locationID, and description.
        
        Raises:
            RuntimeError: If collection creation fails due to schema validation errors,
                         permission issues, or Weaviate service problems.
        """
        try:
            collections = self.client.collections.list_all()
            
            if self.collection_name not in collections:
                logger.info(f"Creating collection: {self.collection_name}")
                
                properties = [
                    Property(name="TicketID", data_type=DataType.TEXT),
                    Property(name="locationID", data_type=DataType.TEXT),
                    Property(name="description", data_type=DataType.TEXT)
                ]
                
                if "active" in self.collection_name.lower():
                    properties.append(
                        Property(name="estimated_resolution_time", data_type=DataType.TEXT)
                    )
                else:
                    properties.append(
                        Property(name="actual_resolution_time", data_type=DataType.TEXT)
                    )
                
                self.client.collections.create(
                    name=self.collection_name,
                    properties=properties
                )
                logger.info(f"Created collection: {self.collection_name}")
            else:
                logger.info(f"Collection {self.collection_name} already exists")
        except Exception as e:
            logger.error(f"Failed to create collection: {e}")
            raise RuntimeError(f"Failed to ensure collection exists: {e}")
    
    def add_documents(self, documents: List[Document]) -> None:
        """
        Add multiple documents to the vector store using efficient batch processing.
        
        Processes a list of Document objects by generating embeddings for each document's
        content and storing them in the Weaviate collection. Uses batch processing to
        optimize performance and provides detailed logging of the operation progress.
        
        Each document's page_content is embedded using Azure OpenAI, and the metadata
        is stored as properties in Weaviate. The method handles partial failures gracefully,
        continuing to process remaining documents even if some individual documents fail.
        
        Args:
            documents (List[Document]): List of Document objects to add to the vector store.
                                      Each Document should have page_content (description)
                                      and metadata containing TicketID, locationID, and
                                      appropriate resolution time fields.
                                      
        Raises:
            RuntimeError: If the batch processing fails completely due to collection access
                         issues, embedding generation failures, or critical Weaviate errors.
                         Individual document failures are logged but do not stop processing.
        """
        try:
            if not documents:
                logger.warning("No documents provided")
                return
            
            collection = self.client.collections.get(self.collection_name)
            batch_size = 50
            successful_adds = 0
            
            for i in range(0, len(documents), batch_size):
                batch_docs = documents[i:i + batch_size]
                
                try:
                    with collection.batch.dynamic() as batch:
                        for doc in batch_docs:
                            try:
                                vector = self.embedding_model.embed_documents([doc.page_content])[0]
                                
                                properties = {
                                    "TicketID": doc.metadata.get("TicketID", ""),
                                    "locationID": doc.metadata.get("locationID", ""),
                                    "description": doc.page_content
                                }
                                
                                if "active" in self.collection_name.lower():
                                    properties["estimated_resolution_time"] = doc.metadata.get("estimated_resolution_time", "")
                                else:
                                    properties["actual_resolution_time"] = doc.metadata.get("actual_resolution_time", "")
                                
                                batch.add_object(properties=properties, vector=vector)
                                successful_adds += 1
                                
                            except Exception as doc_error:
                                logger.warning(f"Failed to add document {doc.metadata.get('TicketID', 'unknown')}: {doc_error}")
                    
                    logger.info(f"Added batch {i//batch_size + 1} ({len(batch_docs)} documents)")
                    
                except Exception as batch_error:
                    logger.error(f"Failed to add batch {i//batch_size + 1}: {batch_error}")
            
            logger.info(f"Successfully added {successful_adds}/{len(documents)} documents")
        except Exception as e:
            raise RuntimeError(f"Failed to add documents to vector store: {e}")
    
    def add_single_document(self, ticket_data: Dict[str, Any]) -> None:
        """
        Add a single ticket document to the vector store with full validation.
        
        Processes an individual ticket by validating required fields, generating embeddings
        for the description, and storing the complete ticket information in Weaviate.
        This method is useful for real-time ticket additions or when processing tickets
        one at a time.
        
        The method validates that all required fields are present and that the description
        meets minimum length requirements before processing. It automatically determines
        the appropriate resolution time field based on the collection type.
        
        Args:
            ticket_data (Dict[str, Any]): Dictionary containing complete ticket information
                                        with required keys:
                                        - description (str): Ticket description content
                                        - TicketID (str): Unique ticket identifier
                                        - locationID (str): Location/site identifier
                                        - estimated_resolution_time (str): ETA for ticket resolution
                                        
        Raises:
            ValueError: If required fields are missing or if the description is too short
                       (less than 5 characters) to provide meaningful search results.
            RuntimeError: If document storage fails due to embedding generation errors,
                         collection access issues, or Weaviate insertion problems.
        """
        try:
            required_fields = ['description', 'TicketID', 'locationID', 'estimated_resolution_time']
            
            for field in required_fields:
                if field not in ticket_data:
                    raise ValueError(f"Missing required field: {field}")
            
            description = ticket_data['description']
            if not description or len(description.strip()) < 5:
                raise ValueError("Description must be at least 5 characters long")
            
            collection = self.client.collections.get(self.collection_name)
            
            vector = self.embedding_model.embed_documents([description])[0]
            
            properties = {
                "TicketID": str(ticket_data['TicketID']),
                "locationID": str(ticket_data['locationID']),
                "description": description
            }
            
            if "active" in self.collection_name.lower():
                properties["estimated_resolution_time"] = str(ticket_data['estimated_resolution_time'])
            else:
                properties["actual_resolution_time"] = str(ticket_data['estimated_resolution_time'])
            
            collection.data.insert(properties=properties, vector=vector)
            logger.info(f"Added ticket {ticket_data['TicketID']} to vector store")
        except Exception as e:
            if isinstance(e, ValueError):
                raise e
            raise RuntimeError(f"Failed to add ticket to vector store: {e}")
    
    def search_similar(self, query: str, locationID: Optional[str] = None, limit: int = 15) -> List[tuple]:
        """
        Search for documents similar to the provided query text using vector similarity.
        
        Performs semantic similarity search by generating an embedding for the query text
        and finding the most similar document vectors in the collection. Supports optional
        location-based filtering to restrict results to specific sites or locations.
        
        The search uses cosine similarity between vector embeddings to find semantically
        similar tickets, which is more effective than keyword-based search for finding
        tickets with similar issues or solutions even when different terminology is used.
        
        Args:
            query (str): Text query to search for similar documents. This will be embedded
                        and compared against stored document vectors to find semantic matches.
            locationID (Optional[str], optional): Filter results to only include tickets
                                                from this specific location. If None, searches
                                                across all locations. Defaults to None.
            limit (int, optional): Maximum number of similar documents to return.
                                 Higher values provide more comprehensive results but may
                                 include less relevant matches. Defaults to 15.
                                 
        Returns:
            List[tuple]: List of tuples where each tuple contains:
                        - Document: Document object with page_content and metadata
                        - float: Similarity score between 0 and 1, where 1 is most similar
                        Results are ordered by similarity score (highest first).
                        
        Raises:
            RuntimeError: If search operation fails due to embedding generation errors,
                         collection access issues, or Weaviate query problems. Returns
                         empty list for non-critical errors to maintain application stability.
        """
        try:
            collection = self.client.collections.get(self.collection_name)
            
            filters = None
            if locationID:
                filters = Filter.by_property("locationID").equal(str(locationID))
            
            vector = self.embedding_model.embed_documents([query])[0]
            response = collection.query.near_vector(
                near_vector=vector,
                limit=limit,
                filters=filters,
                return_metadata=MetadataQuery(distance=True)
            )
            
            results = []
            for obj in response.objects:
                metadata = {
                    "TicketID": obj.properties.get("TicketID", ""),
                    "locationID": obj.properties.get("locationID", ""),
                }
                
                if "estimated_resolution_time" in obj.properties:
                    metadata["estimated_resolution_time"] = obj.properties.get("estimated_resolution_time", "")
                elif "actual_resolution_time" in obj.properties:
                    metadata["actual_resolution_time"] = obj.properties.get("actual_resolution_time", "")
                
                doc = Document(
                    page_content=obj.properties.get("description", ""),
                    metadata=metadata
                )
                
                score = 1 - obj.metadata.distance if obj.metadata.distance is not None else 0.99
                results.append((doc, score))
            
            logger.info(f"Found {len(results)} similar documents")
            return results
        except Exception as e:
            logger.error(f"Search failed: {e}")
            return []
    
    def get_collection(self) -> Dict[str, Any]:
        """
        Retrieve comprehensive information about the current collection state and health.
        
        Provides diagnostic information about the collection including object count,
        operational status, and any error conditions. This is useful for monitoring
        collection health, debugging issues, and validating that operations completed
        successfully.
        
        Returns:
            Dict[str, Any]: Dictionary containing collection information:
                          - name (str): Collection name
                          - total_objects (int): Number of documents stored (if healthy)
                          - status (str): "healthy" if operational, "error" if problems exist
                          - error (str): Error description if status is "error"
                          
        Raises:
            RuntimeError: If collection information retrieval fails due to severe
                         connectivity or permission issues. For minor errors, returns
                         error status in the result dictionary instead of raising.
        """
        try:
            collection = self.client.collections.get(self.collection_name)
            aggregate = collection.aggregate.over_all(total_count=True)
            
            return {
                "name": self.collection_name,
                "total_objects": aggregate.total_count,
                "status": "healthy"
            }
        except Exception as e:
            logger.error(f"Could not get collection info: {e}")
            return {"name": self.collection_name, "status": "error", "error": str(e)}
    
    def close(self):
        """
        Properly close the Weaviate client connection and clean up resources.
        
        Ensures that the Weaviate client connection is properly terminated and resources
        are released. This should be called when the VectorStoreManager is no longer
        needed to prevent connection leaks and ensure clean shutdown.
        
        The method handles cases where the client may already be closed or never
        properly initialized, making it safe to call multiple times or in cleanup
        scenarios.
        
        Raises:
            RuntimeError: If connection cleanup fails due to unexpected errors during
                         the close operation, though this is logged and handled gracefully.
        """
        try:
            if hasattr(self, 'client') and self.client:
                self.client.close()
                logger.info("Closed Weaviate connection")
        except Exception as e:
            logger.error(f"Error closing connection: {e}")
            raise RuntimeError(f"Failed to close Weaviate connection: {e}")