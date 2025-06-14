import json
import hashlib
import logging
from typing import Dict, Any, Tuple, List, Optional
import numpy as np
import redis
from langchain_core.prompts import PromptTemplate
from langchain_openai import AzureChatOpenAI
from azure.search.documents import SearchClient
from azure.identity import DefaultAzureCredential
from azure.core.credentials import AzureKeyCredential
from authorization.authorization import retrive_credential

logger = logging.getLogger(__name__)


class TicketProcessor:
    """
    Processes ticket requests using RAG (Retrieval-Augmented Generation) with Azure AI Search and optional Weaviate.
    
    This class provides a comprehensive ticket processing system that combines multiple search strategies
    to find similar tickets and estimate resolution times. It supports hybrid search approaches using
    both traditional text search and vector similarity search, with intelligent fallback mechanisms
    to ensure every ticket receives appropriate handling.
    
    The processor integrates multiple data sources including Azure AI Search indexes and optional
    Weaviate vector stores for both active and historic tickets. It uses machine learning models
    to generate embeddings for semantic search and employs caching for improved performance.
    
    Key capabilities:
    - Multi-strategy search approach with intelligent fallbacks
    - Hybrid text and vector search for maximum relevance
    - Automatic resolution time estimation based on similar tickets
    - Customer notification generation using AI
    - Redis caching for improved performance
    - Comprehensive error handling and validation
    
    Attributes:
        search_index (str): Name of the Azure AI Search index containing ticket data
        active_vectorstore: Optional Weaviate vector store for active tickets
        history_vectorstore: Optional Weaviate vector store for historic tickets
        embedding_model: Optional model for generating text embeddings
        has_vector_search (bool): Whether vector search capabilities are available
        has_active_vectors (bool): Whether active ticket vector search is available
        has_historic_vectors (bool): Whether historic ticket vector search is available
        redis_client: Optional Redis client for caching
        search_client: Azure AI Search client
        llm: Azure OpenAI language model for text generation
        vector_field_name: Name of the vector field in Azure Search index
    """
    
    def __init__(self, search_index: str, active_vectorstore=None, history_vectorstore=None, embedding_model=None):
        """
        Initialize the TicketProcessor with search capabilities and optional vector stores.
        
        Sets up all required services including Azure AI Search, optional Weaviate vector stores,
        Redis caching, and Azure OpenAI language models. Automatically detects available
        capabilities and configures the processor accordingly.
        
        Args:
            search_index (str): Name of the Azure AI Search index that contains ticket data
            active_vectorstore (optional): Weaviate vector store instance for active tickets.
                                         Enables semantic search on currently open tickets.
            history_vectorstore (optional): Weaviate vector store instance for historic tickets.
                                          Enables semantic search on resolved/completed tickets.
            embedding_model (optional): Model for generating text embeddings for vector search.
                                      Required for hybrid search capabilities in Azure Search.
        """
        self.search_index = search_index
        self.active_vectorstore = active_vectorstore
        self.history_vectorstore = history_vectorstore
        self.embedding_model = embedding_model
        
        self.has_vector_search = bool(active_vectorstore or history_vectorstore)
        self.has_active_vectors = bool(active_vectorstore)
        self.has_historic_vectors = bool(history_vectorstore)
        
        self.redis_client = self._create_redis_client()
        self.search_client = self._create_search_client()
        self.llm = self._create_llm()
        
        self.summarization_prompt = self._create_summarization_prompt()
        self.notification_prompt = self._create_notification_prompt()
        
        self.vector_field_name = self._discover_vector_field()
        
        logger.info(f"TicketProcessor initialized with capabilities:")
        logger.info(f"  - Vector search: {self.has_vector_search}")
        logger.info(f"  - Active vectors: {self.has_active_vectors}")
        logger.info(f"  - Historic vectors: {self.has_historic_vectors}")
        logger.info(f"  - Azure Search vector field: {self.vector_field_name}")
        logger.info(f"  - Azure Search: Available")
    
    def _create_redis_client(self) -> Optional[redis.Redis]:
        """
        Create Redis client for caching query results and improving performance.
        
        Attempts to establish a connection to Redis using the provided URL. If Redis
        is not available or configuration is missing, caching will be disabled but
        the processor will continue to function normally.
        
        Returns:
            Optional[redis.Redis]: Connected Redis client if successful, None if Redis
                                  is unavailable or configuration is missing. When None,
                                  all caching operations are skipped gracefully.
        """
        try:
            redis_url = retrive_credential("REDIS-URL")
            if not redis_url:
                logger.warning("REDIS_URL not provided - caching disabled")
                return None
            return redis.Redis.from_url(redis_url)
        except Exception as e:
            logger.warning(f"Failed to create Redis client: {e} - caching disabled")
            return None
    
    def _create_search_client(self) -> SearchClient:
        """
        Create Azure AI Search client for accessing ticket data and performing searches.
        
        Establishes a connection to Azure AI Search using the configured endpoint and
        credentials. This client is used for all text-based and hybrid search operations
        against the ticket data index.
        
        Returns:
            SearchClient: Configured Azure AI Search client ready for search operations
            
        Raises:
            RuntimeError: If the search client cannot be created due to missing credentials,
                         invalid endpoint configuration, or connection failures.
        """
        try:
            endpoint = retrive_credential("AZURE-SEARCH-ENDPOINT")
            admin_key = retrive_credential("AZURE-SEARCH-ADMIN-KEY")
            
            return SearchClient(
                endpoint=endpoint,
                index_name=self.search_index,
                credential=AzureKeyCredential(admin_key)
            )
        except Exception as e:
            raise RuntimeError(f"Failed to create Azure Search client: {e}")
    
    def _create_llm(self) -> AzureChatOpenAI:
        """
        Create Azure OpenAI language model for text generation and summarization.
        
        Sets up the Azure OpenAI GPT model used for generating customer notifications,
        summarizing ticket descriptions, and other natural language processing tasks.
        Uses Azure Active Directory authentication for secure access.
        
        Returns:
            AzureChatOpenAI: Configured Azure OpenAI language model with appropriate
                           settings for ticket processing tasks (temperature=0 for
                           consistent, deterministic outputs).
                           
        Raises:
            RuntimeError: If the language model cannot be created due to missing Azure
                         OpenAI endpoint, authentication failures, or service unavailability.
        """
        try:
            endpoint = retrive_credential("AZURE-OPENAI-ENDPOINT")
            
            credential = DefaultAzureCredential()
            token_provider = lambda: credential.get_token("https://cognitiveservices.azure.com/.default").token
            
            return AzureChatOpenAI(
                model="gpt-4o-mini",
                azure_endpoint=endpoint,
                azure_deployment="gpt-4o-mini",
                api_version="2024-12-01-preview",
                azure_ad_token_provider=token_provider,
                temperature=0
            )
        except Exception as e:
            raise RuntimeError(f"Failed to create Azure OpenAI LLM: {e}")
    
    def _create_summarization_prompt(self) -> PromptTemplate:
        """
        Create prompt template for summarizing long ticket descriptions.
        
        Returns:
            PromptTemplate: Template for generating concise summaries of ticket content
                          while preserving important technical details and context.
        """
        return PromptTemplate.from_template(
            "Summarize this ticket description concisely:\n{text}\n\nSUMMARY:"
        )
    
    def _create_notification_prompt(self) -> PromptTemplate:
        """
        Create prompt template for generating customer service notifications.
        
        Returns:
            PromptTemplate: Template for creating professional, empathetic customer
                          notifications that include ticket acknowledgment, estimated
                          resolution time, and reassuring messaging.
        """
        return PromptTemplate.from_template(
            """Generate an empathetic customer service notification:
            
            Issue: {description}
            Estimated Resolution: {estimated_time} hours
            Location: {locationID}
            Matching Method: {matching_method}
            
            Create a professional, reassuring message that explains we've received their ticket and provide the estimated resolution time.

            Notification:"""
        )
    
    def _discover_vector_field(self) -> Optional[str]:
        """
        Automatically discover the vector field name in the Azure Search index.
        
        Tests various common vector field names to identify which one is configured
        in the search index for storing document embeddings. This enables hybrid
        search capabilities when embeddings are available.
        
        Returns:
            Optional[str]: Name of the vector field if found and functional, None if
                          no working vector field is discovered or if embedding model
                          is not available.
        """
        if not self.embedding_model:
            return None
        
        try:
            test_vector = [0.1] * 1536
            
            vector_field_names = [
                "content_vector",
                "vector", 
                "embedding",
                "content_embedding",
                "text_vector",
                "embeddings"
            ]
            
            for field_name in vector_field_names:
                try:
                    vector_query = {
                        "kind": "vector",
                        "vector": test_vector,
                        "k": 1,
                        "fields": field_name
                    }
                    
                    test_results = self.search_client.search(
                        search_text=None,
                        vector_queries=[vector_query],
                        top=1
                    )
                    
                    list(test_results)
                    logger.info(f"Discovered vector field: {field_name}")
                    return field_name
                    
                except Exception as e:
                    logger.debug(f"Vector field '{field_name}' not available: {e}")
                    continue
            
            logger.warning("No working vector field found in Azure Search index")
            return None
            
        except Exception as e:
            logger.error(f"Failed to discover vector field: {e}")
            return None
    
    def _validate_query(self, query: str) -> None:
        """
        Validate input query to ensure it meets minimum requirements for processing.
        
        Args:
            query (str): User's ticket description or search query
            
        Raises:
            ValueError: If query is empty, contains only whitespace, or is too short
                       to provide meaningful search results (less than 20 characters).
        """
        if not query or not query.strip():
            raise ValueError("Query cannot be empty")
        if len(query.strip()) < 20:
            raise ValueError("Query too short - please provide more details")
    
    def _summarize_text(self, text: str, max_length: int = 1500) -> str:
        """
        Summarize text content if it exceeds the specified maximum length.
        
        Uses the configured language model to create concise summaries of long ticket
        descriptions while preserving important technical details. Falls back to
        simple truncation if AI summarization fails.
        
        Args:
            text (str): Original text content to potentially summarize
            max_length (int, optional): Maximum allowed text length before summarization
                                      is triggered. Defaults to 1500 characters.
                                      
        Returns:
            str: Original text if short enough, AI-generated summary if available,
                or truncated text with ellipsis as fallback.
        """
        if not isinstance(text, str) or len(text) <= max_length:
            return text if isinstance(text, str) else ""
        
        try:
            summary = self.llm.invoke(self.summarization_prompt.format(text=text))
            return summary.content.strip() if hasattr(summary, 'content') else str(summary).strip()
        except Exception as e:
            logger.warning(f"Summarization failed: {e}")
            return text[:1000] + "..."
    
    def _search_azure_hybrid(self, description: str, locationID: int) -> List[Tuple]:
        """
        Perform hybrid search using both text and vector queries in Azure AI Search.
        
        Combines traditional text search with vector similarity search for optimal
        relevance. If vector capabilities are available, performs hybrid search;
        otherwise falls back to text-only search automatically.
        
        Args:
            description (str): Ticket description to search for similar content
            locationID (int): Location ID to filter results to specific site/location
            
        Returns:
            List[Tuple]: List of tuples containing (Document, relevance_score) for
                        matching tickets, ordered by relevance with highest scores first.
        """
        try:
            self._validate_query(description)
            
            search_params = {
                "search_text": description,
                "filter": f"locationID eq '{locationID}'",
                "select": ["TicketID", "locationID", "estimated_resolution_time", "description"],
                "top": 15
            }
            
            if self.embedding_model and self.vector_field_name:
                try:
                    test_vector = self.embedding_model.embed_documents([description])[0]
                    vector_query = {
                        "kind": "vector",
                        "vector": test_vector,
                        "k": 15,
                        "fields": self.vector_field_name
                    }
                    search_params["vector_queries"] = [vector_query]
                    logger.debug("Using hybrid search (text + vector)")
                except Exception as e:
                    logger.warning(f"Vector query failed, using text-only search: {e}")
            else:
                logger.debug("Using text-only search")
            
            results = self.search_client.search(**search_params)
            
            matches = []
            for result in results:
                from langchain_core.documents import Document
                doc = Document(
                    page_content=result.get("description", ""),
                    metadata={
                        "TicketID": result.get("TicketID", ""),
                        "locationID": result.get("locationID", ""),
                        "estimated_resolution_time": result.get("estimated_resolution_time", "")
                    }
                )
                matches.append((doc, result.get("@search.score", 0.0)))
            
            logger.info(f"Azure Search found {len(matches)} matches using {'hybrid' if self.vector_field_name else 'text-only'} search")
            return matches
            
        except Exception as e:
            logger.error(f"Azure search failed: {e}")
            raise RuntimeError(f"Azure hybrid search failed: {e}")
    
    def _search_azure_text_only(self, description: str, locationID: int) -> List[Tuple]:
        """
        Perform pure text-based search as a fallback when vector search is unavailable.
        
        Uses Azure AI Search's full-text search capabilities with advanced query
        processing to find relevant tickets based on keyword matching and text analysis.
        
        Args:
            description (str): Ticket description to search for similar content
            locationID (int): Location ID to filter results to specific site/location
            
        Returns:
            List[Tuple]: List of tuples containing (Document, relevance_score) for
                        matching tickets based on text similarity.
                        
        Raises:
            RuntimeError: If text search fails due to query processing errors or
                         Azure Search service issues.
        """
        try:
            self._validate_query(description)
            
            results = self.search_client.search(
                search_text=description,
                filter=f"locationID eq '{locationID}'",
                select=["TicketID", "locationID", "estimated_resolution_time", "description"],
                top=15,
                search_mode="all",
                query_type="full"
            )
            
            matches = []
            for result in results:
                from langchain_core.documents import Document
                doc = Document(
                    page_content=result.get("description", ""),
                    metadata={
                        "TicketID": result.get("TicketID", ""),
                        "locationID": result.get("locationID", ""),
                        "estimated_resolution_time": result.get("estimated_resolution_time", "")
                    }
                )
                score = result.get("@search.score", 0.0)
                matches.append((doc, score))
            
            logger.info(f"Text search found {len(matches)} matches")
            return matches
            
        except Exception as e:
            logger.error(f"Text search failed: {e}")
            raise RuntimeError(f"Azure text search failed: {e}")
    
    def _search_vector_store(self, description: str, vectorstore, locationID: int) -> List[Tuple]:
        """
        Search Weaviate vector store for semantically similar tickets.
        
        Uses vector similarity search to find tickets with similar semantic meaning,
        even when different terminology is used. This enables finding relevant
        tickets that traditional keyword search might miss.
        
        Args:
            description (str): Ticket description to find semantic matches for
            vectorstore: Weaviate vector store instance (active or historic)
            locationID (int): Location ID to filter results to specific site/location
            
        Returns:
            List[Tuple]: List of tuples containing (Document, similarity_score) for
                        semantically similar tickets, ordered by similarity with
                        highest scores first.
                        
        Raises:
            RuntimeError: If vector search fails due to embedding generation errors,
                         Weaviate connectivity issues, or query processing problems.
        """
        if not vectorstore:
            logger.debug("Vector store not available")
            return []
        
        try:
            self._validate_query(description)
            results = vectorstore.search_similar(description, str(locationID), limit=15)
            logger.info(f"Vector store found {len(results)} matches")
            return results
        except Exception as e:
            logger.error(f"Vector search failed: {e}")
            raise RuntimeError(f"Vector store search failed: {e}")
    
    def _calculate_estimated_time(self, matches: List[Tuple], ticket_type: str = "active", method: str = "unknown") -> int:
        """
        Calculate estimated resolution time based on similar ticket data.
        
        Analyzes resolution times from similar tickets to provide an accurate
        estimate for the new ticket. Uses different time fields based on whether
        the matches come from active or historic tickets.
        
        Args:
            matches (List[Tuple]): List of similar tickets with their similarity scores
            ticket_type (str, optional): Type of tickets in matches - "active" for
                                       current tickets or "historic" for resolved tickets.
                                       Affects which time field is used. Defaults to "active".
            method (str, optional): Search method used to find matches, for logging
                                  purposes. Defaults to "unknown".
                                  
        Returns:
            int: Estimated resolution time in hours based on average of similar tickets.
                Returns 24 hours as default if no valid matches or time data available.
        """
        if not matches:
            logger.info(f"No matches found for {method}, using default 24h")
            return 24
        
        times = []
        for doc, score in matches:
            try:
                if ticket_type == "active":
                    time_str = doc.metadata.get('estimated_resolution_time', '24')
                else:
                    time_str = doc.metadata.get('actual_resolution_time', '24')
                
                if isinstance(time_str, str):
                    time_str = time_str.strip()
                
                times.append(float(time_str))
            except (ValueError, TypeError):
                times.append(24.0)
        
        avg_time = int(np.mean(times)) if times else 24
        logger.info(f"Calculated average time: {avg_time}h from {len(times)} valid matches using {method}")
        return avg_time
    
    def _create_ticket(self, TicketID: int, customer_id: int, locationID: int, 
                      description: str, estimated_time: int) -> Dict[str, Any]:
        """
        Create a standardized ticket dictionary with all required fields.
        
        Args:
            TicketID (int): Unique identifier for the new ticket
            customer_id (int): Customer identifier associated with the ticket
            locationID (int): Location/site identifier where the issue occurred
            description (str): Ticket description (will be summarized if too long)
            estimated_time (int): Estimated resolution time in hours
            
        Returns:
            Dict[str, Any]: Complete ticket dictionary with all required fields
                           formatted for storage and processing.
        """
        return {
            "TicketID": TicketID,
            "customerID": customer_id,
            "locationID": locationID,
            "type": "complaint",
            "description": self._summarize_text(description),
            "clusterID": 5,
            "estimated_resolution_time": estimated_time
        }
    
    def _generate_notification(self, ticket: Dict[str, Any], matching_method: str = "AI Search") -> str:
        """
        Generate a professional customer service notification message.
        
        Uses the configured language model to create personalized, empathetic
        notifications that acknowledge the customer's ticket and provide clear
        information about estimated resolution time and the process used.
        
        Args:
            ticket (Dict[str, Any]): Complete ticket information for notification context
            matching_method (str, optional): Description of the search method used to
                                           find similar tickets, included in the notification
                                           for transparency. Defaults to "AI Search".
                                           
        Returns:
            str: Professional customer service notification message that can be sent
                to the customer or displayed in the application interface.
        """
        try:
            prompt_input = {
                "description": ticket["description"],
                "estimated_time": ticket["estimated_resolution_time"],
                "locationID": ticket["locationID"],
                "matching_method": matching_method
            }
            
            response = self.llm.invoke(self.notification_prompt.format(**prompt_input))
            return response.content.strip() if hasattr(response, 'content') else str(response).strip()
            
        except Exception as e:
            logger.error(f"Notification generation failed: {e}")
            return f"We've received your ticket and are working to resolve it within {ticket['estimated_resolution_time']} hours. Our team has analyzed similar issues to provide this estimate."
    
    def _get_next_ids(self) -> Tuple[int, int]:
        """
        Determine the next available ticket and customer IDs by analyzing existing data.
        
        Queries the search index to find the highest existing IDs and generates
        the next sequential IDs. Includes robust error handling and fallback to
        random IDs when the index is empty or inaccessible.
        
        Returns:
            Tuple[int, int]: Tuple containing (next_ticket_id, next_customer_id)
                           for use in creating new tickets.
                           
        Raises:
            RuntimeError: If ID generation fails completely due to both search
                         index failure and random ID generation problems.
        """
        try:
            results = self.search_client.search(search_text="*", top=1000, include_total_count=True)
            tickets = list(results)
            
            if tickets:
                TicketIDs = []
                customer_ids = []
                
                for t in tickets:
                    TicketID = t.get("TicketID") or t.get("TicketID") or t.get("id")
                    customer_id = t.get("customer_id") or t.get("customerID") or t.get("customer")
                    
                    if TicketID:
                        try:
                            TicketIDs.append(int(TicketID))
                        except (ValueError, TypeError):
                            pass
                            
                    if customer_id:
                        try:
                            customer_ids.append(int(customer_id))
                        except (ValueError, TypeError):
                            pass
                
                max_TicketID = max(TicketIDs) if TicketIDs else 0
                max_customer_id = max(customer_ids) if customer_ids else 0
                
                logger.info(f"Found {len(tickets)} documents, max ticket ID: {max_TicketID}, max customer ID: {max_customer_id}")
                
            else:
                logger.warning("No documents found in search index")
                max_TicketID = 0
                max_customer_id = 0
            
            return max_TicketID + 1, max_customer_id + 1
            
        except Exception as e:
            logger.error(f"Failed to get next IDs: {e}")
            import random
            TicketID = random.randint(10001, 99999)
            customer_id = random.randint(1001, 9999)
            logger.info(f"Using random IDs - Ticket: {TicketID}, Customer: {customer_id}")
            return TicketID, customer_id
    
    def _cache_result(self, query_key: str, result: Tuple[str, Dict[str, Any]], ttl: int = 3600):
        """
        Cache query results in Redis for improved performance on repeated queries.
        
        Args:
            query_key (str): Unique key identifying the query for caching
            result (Tuple[str, Dict[str, Any]]): Query result to cache
            ttl (int, optional): Time-to-live in seconds. Defaults to 3600 (1 hour).
        """
        if not self.redis_client:
            return
        
        try:
            self.redis_client.setex(query_key, ttl, json.dumps(result))
        except Exception as e:
            logger.warning(f"Caching failed: {e}")
    
    def _get_cached_result(self, query_key: str) -> Optional[Tuple[str, Dict[str, Any]]]:
        """
        Retrieve cached query results if available.
        
        Args:
            query_key (str): Unique key identifying the cached query
            
        Returns:
            Optional[Tuple[str, Dict[str, Any]]]: Cached result if available, None otherwise.
        """
        if not self.redis_client:
            return None
        
        try:
            cached = self.redis_client.get(query_key)
            return json.loads(cached) if cached else None
        except Exception as e:
            logger.warning(f"Cache retrieval failed: {e}")
            return None
    
    def add_ticket_to_search(self, ticket: Dict[str, Any]) -> None:
        """
        Add a newly created ticket to the Azure AI Search index for future searches.
        
        Uploads the ticket data to the search index, including vector embeddings
        if available, to ensure it can be found in future similarity searches.
        
        Args:
            ticket (Dict[str, Any]): Complete ticket data to add to the search index
            
        Raises:
            RuntimeError: If adding the ticket to the search index fails due to
                         document formatting errors or Azure Search service issues.
        """
        try:
            document = {
                "TicketID": str(ticket["TicketID"]),
                "locationID": str(ticket["locationID"]),
                "estimated_resolution_time": str(ticket["estimated_resolution_time"]),
                "description": ticket["description"]
            }
            
            if self.embedding_model:
                try:
                    vector = self.embedding_model.embed_documents([ticket["description"]])[0]
                    if self.vector_field_name:
                        document[self.vector_field_name] = vector
                    else:
                        document["content_vector"] = vector
                except Exception as e:
                    logger.warning(f"Failed to create vector for new ticket: {e}")
            
            self.search_client.upload_documents([document])
            logger.info(f"Added ticket {ticket['TicketID']} to search index")
            
        except Exception as e:
            logger.error(f"Failed to add ticket to search: {e}")
            raise RuntimeError(f"Failed to add ticket to search index: {e}")
    
    def process_ticket_request(self, description: str, locationID: int) -> Tuple[str, Dict[str, Any], str]:
        """
        Process a ticket request using multiple search strategies with intelligent fallbacks.
        
        This is the main method that orchestrates the entire ticket processing workflow.
        It attempts multiple search strategies in order of preference, from most sophisticated
        (vector search) to most basic (text search), ensuring every valid ticket receives
        appropriate handling and accurate resolution time estimates.
        
        The method implements a comprehensive fallback strategy:
        1. Check cache for previous identical queries
        2. Try vector search on active tickets (if available)
        3. Try vector search on historic tickets (if available)
        4. Try Azure AI Search with hybrid approach
        5. Try pure text search as final fallback
        6. Try global search without location filter
        7. Return appropriate error/invalid query response
        
        Args:
            description (str): Detailed description of the customer's issue or problem.
                             Must be at least 20 characters for meaningful processing.
            locationID (int): Identifier for the location/site where the issue occurred.
                            Used for filtering search results to relevant geographic area.
                            
        Returns:
            Tuple[str, Dict[str, Any], str]: Tuple containing:
                - ticket_type (str): Classification of the ticket processing result
                  (e.g., 'new_active_ticket', 'invalid_query', 'error')
                - ticket_data (Dict[str, Any]): Complete ticket information including
                  TicketID, customer info, estimated resolution time, etc.
                - notification (str): Customer-facing notification message explaining
                  the ticket status and estimated resolution time
                  
        Raises:
            RuntimeError: If all processing strategies fail due to critical system errors,
                         though the method attempts to return error tickets rather than
                         raise exceptions when possible to maintain application stability.
        """
        try:
            self._validate_query(description)
            
            query_hash = hashlib.sha256(f"{description}:{locationID}".encode()).hexdigest()
            cached_result = self._get_cached_result(query_hash)
            
            if cached_result:
                ticket_type, ticket_data = cached_result
                notification = self._generate_notification(ticket_data, "Cached Result")
                logger.info("Returning cached result")
                return ticket_type, ticket_data, notification
            
            TicketID, customer_id = self._get_next_ids()
            
            if self.has_active_vectors:
                logger.info("Trying vector search on active tickets...")
                active_matches = self._search_vector_store(description, self.active_vectorstore, locationID)
                
                if active_matches:
                    estimated_time = self._calculate_estimated_time(active_matches, "active", "Vector Search (Active)")
                    ticket = self._create_ticket(TicketID, customer_id, locationID, description, estimated_time)
                    notification = self._generate_notification(ticket, "Vector Search - Active Tickets")
                    
                    result = ('new_active_ticket', ticket)
                    self._cache_result(query_hash, result)
                    return result[0], result[1], notification
            
            if self.has_historic_vectors:
                logger.info("Trying vector search on historic tickets...")
                history_matches = self._search_vector_store(description, self.history_vectorstore, locationID)
                
                if history_matches:
                    estimated_time = self._calculate_estimated_time(history_matches, "historic", "Vector Search (Historic)")
                    ticket = self._create_ticket(TicketID, customer_id, locationID, description, estimated_time)
                    notification = self._generate_notification(ticket, "Vector Search - Historic Tickets")
                    
                    result = ('new_historic_ticket', ticket)
                    self._cache_result(query_hash, result)
                    return result[0], result[1], notification
            
            logger.info("Trying Azure AI Search...")
            azure_matches = self._search_azure_hybrid(description, locationID)
            
            if azure_matches:
                estimated_time = self._calculate_estimated_time(azure_matches, "active", "Azure AI Search")
                ticket = self._create_ticket(TicketID, customer_id, locationID, description, estimated_time)
                
                method = "Hybrid Search (Text + Vector)" if self.vector_field_name else "Text Search"
                notification = self._generate_notification(ticket, method)
                
                result = ('new_azure_search_ticket', ticket)
                self._cache_result(query_hash, result)
                return result[0], result[1], notification
            
            logger.info("Trying pure text search fallback...")
            text_matches = self._search_azure_text_only(description, locationID)
            
            if text_matches:
                estimated_time = self._calculate_estimated_time(text_matches, "active", "Text Search")
                ticket = self._create_ticket(TicketID, customer_id, locationID, description, estimated_time)
                notification = self._generate_notification(ticket, "Text Search")
                
                result = ('new_text_search_ticket', ticket)
                self._cache_result(query_hash, result)
                return result[0], result[1], notification
            
            logger.info("Trying search without location filter...")
            try:
                results = self.search_client.search(
                    search_text=description,
                    select=["TicketID", "locationID", "estimated_resolution_time", "description"],
                    top=10
                )
                
                global_matches = []
                for result in results:
                    from langchain_core.documents import Document
                    doc = Document(
                        page_content=result.get("description", ""),
                        metadata={
                            "TicketID": result.get("TicketID", ""),
                            "locationID": result.get("locationID", ""),
                            "estimated_resolution_time": result.get("estimated_resolution_time", "")
                        }
                    )
                    global_matches.append((doc, result.get("@search.score", 0.0)))
                
                if global_matches:
                    estimated_time = self._calculate_estimated_time(global_matches, "active", "Global Search")
                    ticket = self._create_ticket(TicketID, customer_id, locationID, description, estimated_time)
                    notification = self._generate_notification(ticket, "Global Search (No Location Filter)")
                    
                    result = ('new_global_search_ticket', ticket)
                    self._cache_result(query_hash, result)
                    return result[0], result[1], notification
                    
            except Exception as e:
                logger.warning(f"Global search failed: {e}")
            
            logger.info("No matches found in any search method")
            invalid_ticket = {
                "TicketID": TicketID,
                "customerID": customer_id,
                "locationID": locationID,
                "type": "invalid_query",
                "description": "Please provide more specific details about your technical issue.",
                "clusterID": 0,
                "estimated_resolution_time": 0,
                "is_valid": False
            }
            
            notification = "We've received your ticket, but couldn't find similar issues to estimate resolution time. Please provide more specific details about your technical problem so we can better assist you."
            
            result = ('invalid_query', invalid_ticket)
            self._cache_result(query_hash, result)
            return result[0], result[1], notification
            
        except ValueError as ve:
            logger.error(f"Validation error processing ticket request: {ve}")
            
            error_ticket = {
                "TicketID": 0,
                "customerID": 0,
                "locationID": locationID if isinstance(locationID, int) else 0,
                "type": "validation_error",
                "description": str(ve),
                "clusterID": 0,
                "estimated_resolution_time": 0,
                "is_valid": False
            }
            
            error_notification = f"Input validation failed: {str(ve)}"
            return 'validation_error', error_ticket, error_notification
            
        except Exception as e:
            logger.error(f"Error processing ticket request: {e}")
            
            error_ticket = {
                "TicketID": 0,
                "customerID": 0,
                "locationID": locationID if isinstance(locationID, int) else 0,
                "type": "error",
                "description": f"System error occurred: {str(e)}",
                "clusterID": 0,
                "estimated_resolution_time": 0,
                "is_valid": False
            }
            
            error_notification = "We're experiencing technical difficulties. Please try again later or contact support directly."
            return 'error', error_ticket, error_notification