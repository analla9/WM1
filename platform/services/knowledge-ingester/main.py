import os
import time
import logging
import hashlib
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional
from pathlib import Path

from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
from sentence_transformers import SentenceTransformer
from elasticsearch import Elasticsearch, helpers, exceptions as es_exceptions
import chromadb
from chromadb.utils import embedding_functions
from dotenv import load_dotenv

# Assuming text_splitter.py is in the same directory
from text_splitter import markdown_to_text, RecursiveCharacterTextSplitter, count_tokens

# Load environment variables
load_dotenv()

# --- Configuration ---
KNOWLEDGE_BASE_DIR = Path(os.getenv("KNOWLEDGE_BASE_DIR", "/iac/knowledge_base/"))
EMBEDDING_MODEL_NAME = os.getenv("EMBEDDING_MODEL_NAME", "sentence-transformers/all-MiniLM-L6-v2")
ELASTICSEARCH_URL = os.getenv("ELASTICSEARCH_URL", "http://elasticsearch:9200")
CHROMA_HOST = os.getenv("CHROMA_HOST", "chromadb") # Chroma service name in Docker Compose
CHROMA_PORT = int(os.getenv("CHROMA_PORT", "8000")) # Internal port Chroma runs on
CHROMA_COLLECTION_NAME = os.getenv("CHROMA_COLLECTION_NAME", "podi_knowledge_base")
ES_INDEX_NAME = os.getenv("ES_INDEX_NAME", "podi_knowledge_chunks")

# Text Splitting Params
CHUNK_SIZE_TOKENS = int(os.getenv("CHUNK_SIZE_TOKENS", 512))
CHUNK_OVERLAP_TOKENS = int(os.getenv("CHUNK_OVERLAP_TOKENS", 50)) # Note: current splitter's overlap is basic

# Logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(module)s - %(message)s')
logger = logging.getLogger(__name__)

# --- Initialize Clients & Models (with retry) ---
def init_clients():
    global es_client, chroma_client, embedding_model, text_splitter

    # Text Splitter
    text_splitter = RecursiveCharacterTextSplitter(chunk_size=CHUNK_SIZE_TOKENS, chunk_overlap=CHUNK_OVERLAP_TOKENS)
    logger.info("Text splitter initialized.")

    # Embedding Model
    max_retries = 5
    retry_delay = 10
    for attempt in range(max_retries):
        try:
            logger.info(f"Loading sentence-transformer model: {EMBEDDING_MODEL_NAME}")
            embedding_model = SentenceTransformer(EMBEDDING_MODEL_NAME)
            logger.info("Embedding model loaded successfully.")
            break
        except Exception as e:
            logger.error(f"Failed to load embedding model (attempt {attempt+1}/{max_retries}): {e}")
            if attempt + 1 == max_retries:
                raise
            time.sleep(retry_delay)

    # Elasticsearch Client
    for attempt in range(max_retries):
        try:
            es_client = Elasticsearch(ELASTICSEARCH_URL, request_timeout=30, max_retries=3, retry_on_timeout=True)
            if not es_client.ping():
                raise ConnectionError("Elasticsearch ping failed")
            logger.info(f"Connected to Elasticsearch at {ELASTICSEARCH_URL}")
            # Create index if it doesn't exist
            if not es_client.indices.exists(index=ES_INDEX_NAME):
                es_index_body = {
                    "mappings": {
                        "properties": {
                            "chunk_id": {"type": "keyword"},
                            "source_document_name": {"type": "keyword"},
                            "source_document_uri": {"type": "keyword"},
                            "chunk_index": {"type": "integer"},
                            "chunk_hash": {"type": "keyword"},
                            "chunk_text": {"type": "text", "analyzer": "standard"},
                            "document_type": {"type": "keyword"},
                            "tags": {"type": "keyword"},
                            "last_modified_document": {"type": "date"},
                            "ingestion_date": {"type": "date"},
                            "token_count": {"type": "integer"}
                        }
                    }
                }
                es_client.indices.create(index=ES_INDEX_NAME, body=es_index_body)
                logger.info(f"Created Elasticsearch index: {ES_INDEX_NAME}")
            break
        except (es_exceptions.ConnectionError, ConnectionRefusedError) as e:
            logger.error(f"Failed to connect to Elasticsearch (attempt {attempt+1}/{max_retries}): {e}")
            if attempt + 1 == max_retries:
                raise
            time.sleep(retry_delay)

    # ChromaDB Client
    # Note: chromadb.HttpClient is the way to connect to a remote Chroma server
    for attempt in range(max_retries):
        try:
            chroma_client = chromadb.HttpClient(host=CHROMA_HOST, port=CHROMA_PORT) # settings=chromadb.Settings(anonymized_telemetry=False)
            chroma_client.heartbeat() # Check connection
            logger.info(f"Connected to ChromaDB at {CHROMA_HOST}:{CHROMA_PORT}")

            # Get or create collection with the specified embedding function for the model
            # ChromaDB's HuggingFaceEmbeddingFunction can be used if HF API token is available and model is on Hub.
            # Since we load SentenceTransformer locally, we generate embeddings ourselves.
            # ChromaDB can accept pre-computed embeddings.
            # If providing embeddings directly, no embedding_function needed for collection, or use a dummy one.
            # For `sentence-transformers/all-MiniLM-L6-v2`, dimension is 384.
            # We need to tell Chroma the dimensionality if we provide embeddings.

            # Option 1: Let Chroma handle embeddings (requires model to be usable by Chroma's default or specified EF)
            # hf_ef = embedding_functions.HuggingFaceEmbeddingFunction(api_key="YOUR_HF_TOKEN_IF_NEEDED", model_name=EMBEDDING_MODEL_NAME)
            # collection = chroma_client.get_or_create_collection(name=CHROMA_COLLECTION_NAME, embedding_function=hf_ef)

            # Option 2: Provide embeddings ourselves (preferred as we have the model loaded)
            # For this, Chroma just needs metadata about the embedding function if it's to validate.
            # Or, if we always provide embeddings, it might not need an EF at collection level.
            # Let's ensure the collection exists. The `embedding_function` param at collection level
            # is for when you pass `documents` and expect Chroma to embed them.
            # If you pass `embeddings` directly, this is less critical.
            # For `add()` with your own embeddings, `embedding_function` in `get_or_create_collection` can be omitted or set to a compatible one.
            # However, it's good practice to specify metadata for consistency.
            # For SentenceTransformer, the metadata for Chroma would be:
            # collection_metadata = {"hnsw:space": "cosine", "embedding_dim": 384} # Example

            # Simplest for providing own embeddings:
            chroma_client.get_or_create_collection(name=CHROMA_COLLECTION_NAME)
            logger.info(f"ChromaDB collection '{CHROMA_COLLECTION_NAME}' accessed/created.")
            break
        except Exception as e: # Catch broader exceptions for Chroma connection initially
            logger.error(f"Failed to connect/setup ChromaDB (attempt {attempt+1}/{max_retries}): {e}")
            if attempt + 1 == max_retries:
                raise
            time.sleep(retry_delay)

es_client: Optional[Elasticsearch] = None
chroma_client: Optional[chromadb.API] = None
embedding_model: Optional[SentenceTransformer] = None
text_splitter: Optional[RecursiveCharacterTextSplitter] = None

init_clients() # Initialize on script start

# --- Core Ingestion Logic ---
def generate_chunk_id(doc_name: str, chunk_index: int) -> str:
    return f"{doc_name}-{chunk_index}"

def get_file_hash(filepath: Path) -> str:
    hasher = hashlib.md5()
    with open(filepath, 'rb') as f:
        buf = f.read()
        hasher.update(buf)
    return hasher.hexdigest()

def process_document(filepath: Path):
    logger.info(f"Processing document: {filepath.name}")
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            md_content = f.read()
    except Exception as e:
        logger.error(f"Failed to read file {filepath}: {e}")
        return

    # Get document metadata
    doc_name = filepath.name
    doc_uri = filepath.as_uri()
    try:
        doc_last_modified_timestamp = datetime.fromtimestamp(filepath.stat().st_mtime, tz=timezone.utc).isoformat()
    except Exception: # Handle potential OS errors on stat
        doc_last_modified_timestamp = datetime.now(timezone.utc).isoformat()

    plain_text = markdown_to_text(md_content)
    chunks = text_splitter.split_text(plain_text)

    if not chunks:
        logger.info(f"No text chunks generated for {doc_name}. Skipping.")
        return

    logger.info(f"Generated {len(chunks)} chunks for {doc_name}.")

    es_actions = []
    chroma_embeddings = []
    chroma_documents = []
    chroma_metadatas = []
    chroma_ids = []

    for i, chunk_text in enumerate(chunks):
        chunk_idx = i
        chunk_id = generate_chunk_id(doc_name, chunk_idx)
        chunk_hash = hashlib.sha256(chunk_text.encode('utf-8')).hexdigest()
        token_cnt = count_tokens(chunk_text)

        # Check if chunk already exists and is unchanged in ES (optional optimization)
        # For simplicity in Phase 4, we might re-ingest, but this is where you'd add change detection.
        # try:
        #     existing_doc = es_client.get(index=ES_INDEX_NAME, id=chunk_id, ignore=[404])
        #     if existing_doc.get('found') and existing_doc['_source'].get('chunk_hash') == chunk_hash:
        #         logger.debug(f"Chunk {chunk_id} already exists and is unchanged. Skipping.")
        #         continue
        # except Exception as e_check:
        #     logger.warning(f"Could not check existing doc {chunk_id} in ES: {e_check}")


        # 1. Generate Embedding
        try:
            embedding = embedding_model.encode(chunk_text, convert_to_tensor=False).tolist() # type: ignore
        except Exception as e:
            logger.error(f"Failed to generate embedding for chunk {chunk_id} from {doc_name}: {e}")
            continue

        current_time_iso = datetime.now(timezone.utc).isoformat()

        # 2. Prepare for Elasticsearch
        es_doc = {
            "_index": ES_INDEX_NAME,
            "_id": chunk_id,
            "_source": {
                "chunk_id": chunk_id,
                "source_document_name": doc_name,
                "source_document_uri": doc_uri,
                "chunk_index": chunk_idx,
                "chunk_hash": chunk_hash,
                "chunk_text": chunk_text,
                "document_type": "runbook", # Placeholder, could extract from doc
                "tags": ["markdown", doc_name.split('.')[0]], # Placeholder
                "last_modified_document": doc_last_modified_timestamp,
                "ingestion_date": current_time_iso,
                "token_count": token_cnt
            }
        }
        es_actions.append(es_doc)

        # 3. Prepare for ChromaDB
        chroma_documents.append(chunk_text)
        chroma_embeddings.append(embedding)
        chroma_metadatas.append({
            "source_document_name": doc_name,
            "source_document_uri": doc_uri,
            "chunk_index": chunk_idx,
            "chunk_hash": chunk_hash,
            "document_type": "runbook",
            "tags": f"{doc_name.split('.')[0]}", # Chroma metadata values must be str, int, float, or bool
            "last_modified_document": doc_last_modified_timestamp,
            "ingestion_date": current_time_iso,
            "token_count": token_cnt
        })
        chroma_ids.append(chunk_id)

    # Bulk ingest into Elasticsearch
    if es_actions:
        try:
            helpers.bulk(es_client, es_actions)
            logger.info(f"Successfully ingested {len(es_actions)} chunks from {doc_name} into Elasticsearch.")
        except helpers.BulkIndexError as e:
            logger.error(f"Elasticsearch bulk ingestion error for {doc_name}: {e.errors}")
        except Exception as e:
            logger.error(f"Unexpected Elasticsearch error for {doc_name}: {e}")


    # Upsert into ChromaDB
    if chroma_ids:
        try:
            collection = chroma_client.get_collection(name=CHROMA_COLLECTION_NAME)
            # Chroma's add method also handles updates if IDs exist (upsert behavior)
            collection.add(
                ids=chroma_ids,
                embeddings=chroma_embeddings,
                documents=chroma_documents,
                metadatas=chroma_metadatas
            )
            logger.info(f"Successfully upserted {len(chroma_ids)} chunks from {doc_name} into ChromaDB.")
        except Exception as e:
            logger.error(f"ChromaDB upsert error for {doc_name}: {e}", exc_info=True)

def initial_scan():
    logger.info(f"Performing initial scan of knowledge base directory: {KNOWLEDGE_BASE_DIR}")
    if not KNOWLEDGE_BASE_DIR.exists():
        logger.warning(f"Knowledge base directory {KNOWLEDGE_BASE_DIR} does not exist. Creating it.")
        KNOWLEDGE_BASE_DIR.mkdir(parents=True, exist_ok=True)
        # Add a sample file if it's empty for first-time setup
        sample_file_path = KNOWLEDGE_BASE_DIR / "sample_runbook.md"
        if not list(KNOWLEDGE_BASE_DIR.glob("*.md")):
             with open(sample_file_path, "w") as f:
                f.write("# Sample Runbook\n\nThis is a test document for the knowledge ingester.")
             logger.info(f"Created a sample runbook: {sample_file_path}")


    for filepath in KNOWLEDGE_BASE_DIR.glob("*.md"):
        if filepath.is_file():
            process_document(filepath)
    logger.info("Initial scan complete.")


# --- Filesystem Watcher ---
class KnowledgeBaseEventHandler(FileSystemEventHandler):
    def __init__(self):
        super().__init__()
        self.processing_files = {} # To handle rapid events for the same file
        self.debounce_time = 2 # seconds

    def on_any_event(self, event):
        if event.is_directory:
            return
        if event.src_path.endswith(".md"):
            # Debounce logic
            current_time = time.time()
            last_processed_time = self.processing_files.get(event.src_path, 0)
            if current_time - last_processed_time > self.debounce_time:
                self.processing_files[event.src_path] = current_time
                logger.info(f"Detected event: {event.event_type} on {event.src_path}")
                if event.event_type in ['created', 'modified']:
                    process_document(Path(event.src_path))
                # elif event.event_type == 'deleted':
                #     # Handle deletion from ES and Chroma if needed
                #     logger.info(f"File deleted: {event.src_path}. Deletion logic not yet implemented.")
                #     pass
            else:
                logger.debug(f"Debounced event for {event.src_path}")


# --- Main Execution ---
if __name__ == "__main__":
    if not all([es_client, chroma_client, embedding_model, text_splitter]):
        logger.critical("One or more critical clients/models failed to initialize. Exiting.")
        exit(1)

    initial_scan()

    event_handler = KnowledgeBaseEventHandler()
    observer = Observer()
    observer.schedule(event_handler, str(KNOWLEDGE_BASE_DIR), recursive=False) # Non-recursive for simplicity
    observer.start()
    logger.info(f"Watching directory {KNOWLEDGE_BASE_DIR} for changes...")

    try:
        while True:
            time.sleep(5) # Keep main thread alive
    except KeyboardInterrupt:
        observer.stop()
        logger.info("Observer stopped. Shutting down.")
    except Exception as e:
        logger.error(f"Unhandled exception in main loop: {e}", exc_info=True)
        observer.stop()
    finally:
        observer.join()
        logger.info("Knowledge Ingester service stopped.")
