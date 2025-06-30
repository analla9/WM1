import os
import json
import logging
import asyncio
from typing import List, Dict, Any, Optional

import httpx # For actual LLM calls if implemented
from fastapi import FastAPI, HTTPException, Body
from pydantic import ValidationError
from sentence_transformers import SentenceTransformer
from elasticsearch import Elasticsearch, exceptions as es_exceptions
import chromadb
from kafka import KafkaConsumer, KafkaProducer # Consumer for incidents, Producer for potential follow-up actions
from kafka.errors import KafkaError
from dotenv import load_dotenv

from .models import IncidentPayload, RemediationPlan, RemediationStep, RetrievedContextItem, RemediationStepParameters

# Load environment variables
load_dotenv()

# --- Configuration ---
KAFKA_BOOTSTRAP_SERVERS = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "kafka:9092").split(',')
KAFKA_INCIDENTS_TOPIC = os.getenv("KAFKA_INCIDENTS_TOPIC", "incidents.detected")
KAFKA_CONSUMER_GROUP_ID = os.getenv("KAFKA_REMEDIATION_CONSUMER_GROUP", "remediation-service-group")

ELASTICSEARCH_URL = os.getenv("ELASTICSEARCH_URL", "http://elasticsearch:9200")
ES_INDEX_NAME = os.getenv("ES_INDEX_NAME", "podi_knowledge_chunks")
CHROMA_HOST = os.getenv("CHROMA_HOST", "chromadb")
CHROMA_PORT = int(os.getenv("CHROMA_PORT", "8000"))
CHROMA_COLLECTION_NAME = os.getenv("CHROMA_COLLECTION_NAME", "podi_knowledge_base")
EMBEDDING_MODEL_NAME = os.getenv("EMBEDDING_MODEL_NAME", "sentence-transformers/all-MiniLM-L6-v2")

LLM_API_URL = os.getenv("LLM_API_URL") # e.g., "https://api.openai.com/v1/chat/completions"
LLM_API_KEY = os.getenv("LLM_API_KEY")
LLM_MODEL_NAME = os.getenv("LLM_MODEL_NAME", "gpt-3.5-turbo") # Example

MAX_CONTEXT_CHUNKS_ES = 3
MAX_CONTEXT_CHUNKS_CHROMA = 3
MAX_TOTAL_CONTEXT_CHUNKS = 5 # Combined

# Logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(module)s - %(message)s')
logger = logging.getLogger(__name__)

# --- Initialize Clients & Models (with retry) ---
es_client: Optional[Elasticsearch] = None
chroma_client: Optional[chromadb.API] = None
embedding_model: Optional[SentenceTransformer] = None
kafka_producer: Optional[KafkaProducer] = None # For publishing results or new actions

async def init_clients():
    global es_client, chroma_client, embedding_model, kafka_producer
    max_retries = 5
    retry_delay = 10

    logger.info(f"Loading sentence-transformer model: {EMBEDDING_MODEL_NAME}")
    embedding_model = SentenceTransformer(EMBEDDING_MODEL_NAME)
    logger.info("Embedding model loaded successfully.")

    for attempt in range(max_retries):
        try:
            es_client = Elasticsearch(ELASTICSEARCH_URL, request_timeout=30, max_retries=3, retry_on_timeout=True)
            if not await es_client.ping(): # Use async ping if available or wrap sync ping
                raise ConnectionError("Elasticsearch ping failed")
            logger.info(f"Connected to Elasticsearch at {ELASTICSEARCH_URL}")
            break
        except Exception as e:
            logger.error(f"Failed to connect to Elasticsearch (attempt {attempt+1}/{max_retries}): {e}")
            if attempt + 1 == max_retries: raise
            await asyncio.sleep(retry_delay)

    for attempt in range(max_retries):
        try:
            chroma_client = chromadb.HttpClient(host=CHROMA_HOST, port=CHROMA_PORT)
            chroma_client.heartbeat()
            logger.info(f"Connected to ChromaDB at {CHROMA_HOST}:{CHROMA_PORT}")
            break
        except Exception as e:
            logger.error(f"Failed to connect/setup ChromaDB (attempt {attempt+1}/{max_retries}): {e}")
            if attempt + 1 == max_retries: raise
            await asyncio.sleep(retry_delay)

    # Initialize Kafka Producer (optional, if this service needs to produce messages)
    # For now, we are just logging the plan. If it needs to publish the plan, uncomment this.
    # for attempt in range(max_retries):
    #     try:
    #         kafka_producer = KafkaProducer(
    #             bootstrap_servers=KAFKA_BOOTSTRAP_SERVERS,
    #             value_serializer=lambda v: json.dumps(v).encode('utf-8')
    #         )
    #         logger.info("Kafka Producer initialized successfully.")
    #         break
    #     except KafkaError as e:
    #         logger.error(f"Kafka Producer initialization failed (attempt {attempt+1}/{max_retries}): {e}")
    #         if attempt + 1 == max_retries: kafka_producer = None # Proceed without producer if it fails
    #         await asyncio.sleep(retry_delay)


app = FastAPI(
    title="Remediation Service",
    version="0.1.0",
    description="Generates remediation plans for incidents using RAG.",
    on_startup=[init_clients] # Ensure clients are initialized when FastAPI app starts
)

# --- RAG Workflow Implementation ---

async def retrieve_from_elasticsearch(query: str, incident_id: str) -> List[RetrievedContextItem]:
    if not es_client:
        logger.error(f"[{incident_id}] Elasticsearch client not initialized. Skipping ES retrieval.")
        return []
    try:
        # Simple keyword query, can be made more sophisticated
        es_query = {
            "query": {
                "multi_match": {
                    "query": query,
                    "fields": ["chunk_text", "source_document_name", "tags^2"], # Boost tags
                    "fuzziness": "AUTO"
                }
            },
            "size": MAX_CONTEXT_CHUNKS_ES
        }
        response = await es_client.search(index=ES_INDEX_NAME, body=es_query) # type: ignore

        contexts = []
        for hit in response['hits']['hits']:
            contexts.append(RetrievedContextItem(
                source_document_name=hit['_source'].get('source_document_name', 'Unknown Source'),
                chunk_id=hit['_id'],
                relevance_score=hit.get('_score'), # Elasticsearch score
                text_snippet=hit['_source'].get('chunk_text', '')[:500] + "..." # Truncate for brevity
            ))
        logger.info(f"[{incident_id}] Retrieved {len(contexts)} contexts from Elasticsearch for query: '{query}'")
        return contexts
    except es_exceptions.NotFoundError:
        logger.warning(f"[{incident_id}] Elasticsearch index '{ES_INDEX_NAME}' not found.")
        return []
    except Exception as e:
        logger.error(f"[{incident_id}] Error retrieving from Elasticsearch: {e}", exc_info=True)
        return []

async def retrieve_from_chromadb(query: str, incident_id: str) -> List[RetrievedContextItem]:
    if not chroma_client or not embedding_model:
        logger.error(f"[{incident_id}] ChromaDB client or embedding model not initialized. Skipping Chroma retrieval.")
        return []
    try:
        collection = chroma_client.get_collection(name=CHROMA_COLLECTION_NAME)
        query_embedding = embedding_model.encode(query, convert_to_tensor=False).tolist() # type: ignore

        results = collection.query(
            query_embeddings=[query_embedding],
            n_results=MAX_CONTEXT_CHUNKS_CHROMA,
            include=["documents", "metadatas", "distances"] # distances are similarity scores
        )

        contexts = []
        if results and results.get('ids') and results['ids'][0]:
            for i, doc_id in enumerate(results['ids'][0]):
                metadata = results['metadatas'][0][i] if results['metadatas'] and results['metadatas'][0] else {}
                document_text = results['documents'][0][i] if results['documents'] and results['documents'][0] else ""
                distance = results['distances'][0][i] if results['distances'] and results['distances'][0] else None

                contexts.append(RetrievedContextItem(
                    source_document_name=str(metadata.get('source_document_name', 'Unknown Source')),
                    chunk_id=str(doc_id),
                    relevance_score=float(1 - distance) if distance is not None else None, # Convert distance to similarity
                    text_snippet=document_text[:500] + "..." # Truncate for brevity
                ))
        logger.info(f"[{incident_id}] Retrieved {len(contexts)} contexts from ChromaDB for query: '{query}'")
        return contexts
    except Exception as e:
        logger.error(f"[{incident_id}] Error retrieving from ChromaDB: {e}", exc_info=True)
        return []

def combine_and_rank_contexts(es_contexts: List[RetrievedContextItem], chroma_contexts: List[RetrievedContextItem], incident_id: str) -> List[RetrievedContextItem]:
    # Simple combination: add all and then sort by score (if available) or just limit
    # More advanced: Reciprocal Rank Fusion (RRF) or other ranking algorithms
    combined = es_contexts + chroma_contexts

    # Remove duplicates by chunk_id, keeping the one with better score if scores exist
    unique_contexts_dict: Dict[str, RetrievedContextItem] = {}
    for ctx in combined:
        if ctx.chunk_id not in unique_contexts_dict or \
           (ctx.relevance_score is not None and unique_contexts_dict[ctx.chunk_id].relevance_score is not None and ctx.relevance_score > unique_contexts_dict[ctx.chunk_id].relevance_score) or \
           (ctx.relevance_score is not None and unique_contexts_dict[ctx.chunk_id].relevance_score is None):
            unique_contexts_dict[ctx.chunk_id] = ctx

    sorted_contexts = sorted(
        list(unique_contexts_dict.values()),
        key=lambda x: x.relevance_score if x.relevance_score is not None else 0,
        reverse=True
    )
    final_contexts = sorted_contexts[:MAX_TOTAL_CONTEXT_CHUNKS]
    logger.info(f"[{incident_id}] Combined and ranked contexts. Total unique: {len(unique_contexts_dict)}, selected top: {len(final_contexts)}")
    return final_contexts


async def generate_llm_prompt(incident: IncidentPayload, contexts: List[RetrievedContextItem]) -> str:
    context_str = "\n\n---\n\n".join([f"Source: {ctx.source_document_name} (Chunk ID: {ctx.chunk_id}, Relevance: {ctx.relevance_score:.2f})\nContent:\n{ctx.text_snippet}" for ctx in contexts])

    prompt = f"""
Incident Details:
ID: {incident.incident_id}
Title: {incident.title}
Description: {incident.description}
Priority: {incident.priority}
Affected Resources: {json.dumps(incident.affected_resources)}
Telemetry Data: {json.dumps(incident.telemetry_data)}
Additional Context from Incident: {json.dumps(incident.additional_context)}

Retrieved Knowledge Base Context:
{context_str if contexts else "No relevant context found in knowledge base."}

Task:
Based on the incident details and the retrieved knowledge base context, provide:
1. A concise Root Cause Analysis.
2. A step-by-step executable Remediation Plan. The plan must be in a structured JSON format as specified below. Each step must have a 'step_number', 'title', 'description', 'action_type', 'parameters' (specific to action_type), and 'expected_outcome'.
   Valid action_types are: "api_call", "run_script", "execute_command", "manual_intervention", "webhook", "kafka_message".
   Ensure parameters are detailed enough for execution. For example, for 'api_call', specify 'service_name', 'endpoint', 'method', and 'payload'. For 'run_script', specify 'target_host_selector' and 'command_or_script_path'.

Output Format (Strict JSON only, no extra text before or after the JSON block):
{{
  "incident_id": "{incident.incident_id}",
  "confidence_score": <float between 0.0 and 1.0>,
  "root_cause_analysis": "<Your analysis here>",
  "retrieved_context": [{{"source_document_name": "...", "chunk_id": "...", "relevance_score": <float>, "text_snippet": "..."}}, ...],
  "remediation_plan": [
    {{
      "step_number": 1,
      "title": "<Short title for step 1>",
      "description": "<Detailed description of step 1>",
      "action_type": "<action_type_enum>",
      "target_resource_id": "<Optional: ID of resource step targets>",
      "parameters": {{ ...parameters specific to action_type... }},
      "expected_outcome": "<Expected result of step 1>"
    }},
    // ... more steps
  ]
}}
"""
    return prompt.strip()

async def call_llm_api(prompt: str, incident_id: str) -> Optional[Dict[str, Any]]:
    if not LLM_API_URL or not LLM_API_KEY:
        logger.warning(f"[{incident_id}] LLM_API_URL or LLM_API_KEY not configured. Skipping actual LLM call.")
        return None # Will trigger mock if None

    headers = {
        "Authorization": f"Bearer {LLM_API_KEY}",
        "Content-Type": "application/json"
    }
    payload = {
        "model": LLM_MODEL_NAME,
        "messages": [{"role": "user", "content": prompt}],
        "response_format": {"type": "json_object"} # If using OpenAI or compatible API that supports JSON mode
        # "temperature": 0.5, # Adjust creativity
    }

    logger.info(f"[{incident_id}] Calling LLM API at {LLM_API_URL} with model {LLM_MODEL_NAME}.")
    async with httpx.AsyncClient(timeout=120.0) as client: # Increased timeout for LLM
        try:
            response = await client.post(LLM_API_URL, json=payload, headers=headers)
            response.raise_for_status()
            llm_response_data = response.json()

            # Extract content assuming OpenAI like structure
            # This part needs to be robust based on the specific LLM API
            if llm_response_data.get("choices") and llm_response_data["choices"][0].get("message"):
                content_str = llm_response_data["choices"][0]["message"].get("content")
                if content_str:
                    logger.info(f"[{incident_id}] Received raw content from LLM: {content_str[:200]}...") # Log snippet
                    return json.loads(content_str) # Expecting LLM to return valid JSON string
            logger.error(f"[{incident_id}] Unexpected LLM API response structure: {llm_response_data}")
            return None
        except httpx.HTTPStatusError as e:
            logger.error(f"[{incident_id}] LLM API request failed: {e.response.status_code} - {e.response.text}")
            return None
        except (json.JSONDecodeError, Exception) as e:
            logger.error(f"[{incident_id}] Error processing LLM response: {e}", exc_info=True)
            return None


async def generate_mock_remediation_plan(incident: IncidentPayload, contexts: List[RetrievedContextItem]) -> RemediationPlan:
    logger.info(f"[{incident.incident_id}] Generating MOCK remediation plan.")
    # This mock should be sophisticated enough to demonstrate the structure.
    # It can use some info from the incident or contexts.

    rca = f"Mock RCA for incident '{incident.title}'. CPU utilization is high ({incident.telemetry_data.get('cpu_utilization', 'N/A')}). "
    if contexts:
        rca += f"Found related context from '{contexts[0].source_document_name}' regarding similar issues."
    else:
        rca += "No specific context found in knowledge base, proceeding with generic steps."

    plan_steps = [
        RemediationStep(
            step_number=1,
            title="Acknowledge Incident & Notify Team",
            description=f"Acknowledge incident {incident.incident_id} and notify the on-call team via Slack.",
            action_type="webhook",
            target_resource_id=incident.affected_resources[0].get("id") if incident.affected_resources else None,
            parameters=RemediationStepParameters(
                url="https_hooks.slack.com_services_YOUR_SLACK_WEBHOOK_URL", # Placeholder
                method="POST",
                payload={
                    "text": f":rotating_light: Incident *{incident.incident_id}*: {incident.title} - Remediation Started. RCA: {rca[:100]}..."
                }
            ),
            expected_outcome="Incident acknowledged and team notified on Slack."
        ),
        RemediationStep(
            step_number=2,
            title="Run Basic Diagnostics on Affected Resource",
            description=f"Execute standard diagnostic script `collect_system_stats.sh` on affected resource(s) like '{incident.affected_resources[0].get('name', 'N/A') if incident.affected_resources else 'target'}'.",
            action_type="run_script",
            target_resource_id=incident.affected_resources[0].get("id") if incident.affected_resources else None,
            parameters=RemediationStepParameters(
                target_host_selector=incident.affected_resources[0].get("name", "target_host") if incident.affected_resources else "target_host",
                command_or_script_path="/opt/scripts/diagnostics/collect_system_stats.sh",
                arguments=["--incident-id", incident.incident_id, "--output-dir", "/tmp/diagnostics"]
            ),
            expected_outcome="Diagnostic script completed, output saved to /tmp/diagnostics on the target."
        )
    ]

    if "database" in incident.title.lower() or (incident.affected_resources and "database" in incident.affected_resources[0].get("type","").lower()):
        plan_steps.append(RemediationStep(
            step_number=3,
            title="Check Database Specific Metrics",
            description="Query database monitoring for active long-running queries and connection pool status.",
            action_type="api_call",
            target_resource_id=incident.affected_resources[0].get("id") if incident.affected_resources else None,
            parameters=RemediationStepParameters(
                service_name="prometheus_query_service", # Hypothetical
                endpoint="/api/v1/query_range",
                method="POST",
                payload={
                    "query": f"sum(irate(pg_stat_activity_count{{instance='{incident.affected_resources[0].get('name', 'unknown_db')}',state='active'}}[5m]))",
                    "start": "-1h", "end": "now", "step": "1m"
                }
            ),
            expected_outcome="Database specific metrics retrieved and available for analysis."
        ))
        plan_steps.append(RemediationStep(
            step_number=4,
            title="Manual Review Required",
            description="Based on diagnostics and metrics, a manual review by a Database Administrator is required to determine if any queries need termination or if resource scaling is necessary.",
            action_type="manual_intervention",
            parameters=RemediationStepParameters(additional_properties={"assigned_team": "DBA On-Call"}), # Using additional_properties
            expected_outcome="DBA team engaged and reviewing the incident."
        ))


    return RemediationPlan(
        incident_id=incident.incident_id,
        confidence_score=0.65, # Mock confidence
        root_cause_analysis=rca,
        retrieved_context=contexts[:2], # Show some retrieved context
        remediation_plan=plan_steps
    )

async def process_incident_for_remediation(incident: IncidentPayload) -> RemediationPlan:
    logger.info(f"[{incident.incident_id}] Starting RAG workflow.")

    # 1. Query Formulation (simple for now, use description and title)
    search_query = f"{incident.title} {incident.description}"

    # 2. Retrieval (run in parallel)
    es_contexts_task = retrieve_from_elasticsearch(search_query, incident.incident_id)
    chroma_contexts_task = retrieve_from_chromadb(search_query, incident.incident_id)
    es_contexts, chroma_contexts = await asyncio.gather(es_contexts_task, chroma_contexts_task)

    combined_contexts = combine_and_rank_contexts(es_contexts, chroma_contexts, incident.incident_id)

    # 3. Augmentation (Prompt Engineering)
    llm_prompt = await generate_llm_prompt(incident, combined_contexts)
    # logger.debug(f"[{incident.incident_id}] Generated LLM Prompt:\n{llm_prompt}") # Can be very verbose

    # 4. Generation
    structured_llm_output: Optional[Dict[str, Any]] = None
    if LLM_API_URL and LLM_API_KEY: # Attempt actual LLM call if configured
        structured_llm_output = await call_llm_api(llm_prompt, incident.incident_id)

    final_plan: RemediationPlan
    if structured_llm_output:
        try:
            # Validate the LLM output against our Pydantic model
            final_plan = RemediationPlan(**structured_llm_output)
            # Ensure incident_id from LLM matches original, or override
            if final_plan.incident_id != incident.incident_id:
                logger.warning(f"[{incident.incident_id}] LLM returned a plan with mismatched incident ID ({final_plan.incident_id}). Overriding with original.")
                final_plan.incident_id = incident.incident_id
            logger.info(f"[{incident.incident_id}] Successfully generated and validated remediation plan from LLM.")
        except ValidationError as e:
            logger.error(f"[{incident.incident_id}] LLM output failed Pydantic validation: {e}. Falling back to mock plan.")
            final_plan = await generate_mock_remediation_plan(incident, combined_contexts)
        except Exception as e_parse: # Catch other parsing errors if LLM output is not even dict-like
            logger.error(f"[{incident.incident_id}] Could not parse LLM output as RemediationPlan: {e_parse}. Falling back to mock plan.")
            final_plan = await generate_mock_remediation_plan(incident, combined_contexts)
    else:
        logger.info(f"[{incident.incident_id}] LLM not called or failed. Generating mock remediation plan.")
        final_plan = await generate_mock_remediation_plan(incident, combined_contexts)

    logger.info(f"[{incident.incident_id}] Final Remediation Plan (JSON):\n{final_plan.json(indent=2)}")

    # Optional: Publish the generated plan to another Kafka topic for orchestration worker
    # if kafka_producer:
    #     try:
    #         kafka_producer.send("remediation.plans.generated", value=final_plan.dict(by_alias=True))
    #         logger.info(f"[{incident.incident_id}] Published remediation plan to Kafka.")
    #     except Exception as e:
    #         logger.error(f"[{incident.incident_id}] Failed to publish remediation plan to Kafka: {e}")

    return final_plan

# --- FastAPI Endpoints ---
@app.post("/v1/remediate", response_model=RemediationPlan)
async def http_remediate_incident(incident: IncidentPayload):
    try:
        return await process_incident_for_remediation(incident)
    except Exception as e:
        logger.error(f"[{incident.incident_id}] Unhandled error in /v1/remediate endpoint: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to process incident remediation: {str(e)}")

# --- Kafka Consumer Thread ---
def kafka_consumer_loop():
    logger.info(f"Kafka consumer thread started. Connecting to {KAFKA_BOOTSTRAP_SERVERS} for topic {KAFKA_INCIDENTS_TOPIC}")
    consumer = None
    while True: # Keep trying to connect
        try:
            consumer = KafkaConsumer(
                KAFKA_INCIDENTS_TOPIC,
                bootstrap_servers=KAFKA_BOOTSTRAP_SERVERS,
                auto_offset_reset='earliest',
                group_id=KAFKA_CONSUMER_GROUP_ID,
                value_deserializer=lambda v: json.loads(v.decode('utf-8')),
                consumer_timeout_ms=10000 # Timeout to allow checking loop and graceful exit
            )
            logger.info("Kafka consumer connected successfully.")
            for message in consumer:
                try:
                    incident_data = message.value
                    logger.info(f"Received incident from Kafka topic '{message.topic}': ID {incident_data.get('incident_id', 'N/A')}")
                    incident = IncidentPayload(**incident_data)
                    # Run the async RAG workflow in the main asyncio event loop
                    # from the synchronous Kafka consumer thread.
                    asyncio.run_coroutine_threadsafe(process_incident_for_remediation(incident), asyncio.get_event_loop())
                except ValidationError as e:
                    logger.error(f"Invalid incident data from Kafka: {e.errors()}. Message: {message.value}")
                except Exception as e:
                    logger.error(f"Error processing Kafka message: {e}. Message: {message.value}", exc_info=True)

        except KafkaError as e:
            logger.error(f"Kafka connection/consumer error: {e}. Retrying in 30 seconds...")
            if consumer: consumer.close() # Close before retry
            time.sleep(30)
        except Exception as e: # Catch other unexpected errors in consumer loop
            logger.error(f"Unexpected error in Kafka consumer loop: {e}. Retrying in 30 seconds...", exc_info=True)
            if consumer: consumer.close()
            time.sleep(30)


@app.on_event("startup")
async def startup_event():
    # Clients (ES, Chroma, embedding model) are initialized by app's on_startup via init_clients()
    # Start Kafka consumer in a separate thread
    import threading
    logger.info("Starting Kafka consumer thread...")
    # Ensure an asyncio event loop is running in the main thread for run_coroutine_threadsafe
    try:
        asyncio.get_running_loop()
    except RuntimeError: # No running event loop
        # This should not happen if Uvicorn is running correctly
        logger.error("No running asyncio event loop in main thread for Kafka consumer! This is unexpected with Uvicorn.")
        # As a fallback, try to set one, but this is tricky.
        # loop = asyncio.new_event_loop()
        # asyncio.set_event_loop(loop)
        # threading.Thread(target=lambda: loop.run_forever(), daemon=True).start()


    consumer_thread = threading.Thread(target=kafka_consumer_loop, daemon=True)
    consumer_thread.start()
    logger.info("Remediation Service started successfully with Kafka consumer thread.")

@app.on_event("shutdown")
async def shutdown_event():
    logger.info("Remediation Service shutting down...")
    if es_client:
        await es_client.close()
        logger.info("Elasticsearch client closed.")
    # Chroma client and embedding model don't have explicit close methods usually.
    # Kafka producer might, if used:
    # if kafka_producer:
    #     kafka_producer.flush()
    #     kafka_producer.close()
    #     logger.info("Kafka producer closed.")
    logger.info("Remediation Service shutdown complete.")

# For local testing (not for Docker usually):
# if __name__ == "__main__":
#     import uvicorn
#     uvicorn.run(app, host="0.0.0.0", port=8004) # Choose a unique port
```
