import os
import json
import logging
from typing import Dict, Any

from fastapi import FastAPI, HTTPException, Depends
from pydantic import BaseModel, Field
from kafka import KafkaProducer
from kafka.errors import KafkaError
from dotenv import load_dotenv

# Load environment variables from .env file for local development
load_dotenv()

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# --- Configuration ---
KAFKA_BOOTSTRAP_SERVERS = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "kafka:9092").split(',')
KAFKA_TASKS_TOPIC = "tasks"
KAFKA_BLUEPRINT_DEPLOYMENT_TOPIC = "blueprint.deployment.requested"
KAFKA_INCIDENTS_DETECTED_TOPIC = "incidents.detected" # Added for Phase 4


# --- Pydantic Models ---
class HealthResponse(BaseModel):
    status: str = "ok"

class AuthTokenRequest(BaseModel):
    username: str
    password: str # In a real scenario, this would be more complex (e.g., grant_type)

class AuthTokenResponse(BaseModel):
    access_token: str
    token_type: str

class JobPayload(BaseModel):
    job_id: str
    task_name: str
    parameters: Dict[str, Any] = Field(default_factory=dict)

class JobSubmissionResponse(BaseModel):
    message: str
    job_id: str
    kafka_offset: int | None = None # Store offset if successfully sent

class BlueprintDeploymentRequest(BaseModel):
    blueprint_yaml: str # Expecting raw YAML string in the request body
    # Could also accept a JSON representation of the blueprint and convert to YAML here if preferred

class BlueprintDeploymentResponse(BaseModel):
    message: str
    blueprint_id: str # The ID from the path parameter
    kafka_topic: str
    kafka_offset: int | None = None

# For Phase 4: Incident Test Endpoint
class TestIncidentPayload(BaseModel):
    incident_id: str = Field(default_factory=lambda: f"INC-TEST-{int(time.time())}")
    title: str = "Test Incident: High Latency Detected"
    description: str = "This is a test incident to trigger the RAG remediation workflow."
    priority: Optional[str] = "P2"
    affected_resources: List[Dict[str, Any]] = Field(default_factory=lambda: [{"type": "service", "id": "cart-service", "name": "ShoppingCartService"}])
    telemetry_data: Optional[Dict[str, Any]] = Field(default_factory=lambda: {"latency_ms": 1500, "error_rate_percent": 5})
    additional_context: Optional[Dict[str, Any]] = Field(default_factory=dict)

class TestIncidentResponse(BaseModel):
    message: str
    incident_id: str
    kafka_topic: str
    kafka_offset: int | None = None


# --- Kafka Producer ---
# It's better to initialize the producer globally if the app is not expected to fork,
# or manage its lifecycle with FastAPI startup/shutdown events for robustness.
try:
    producer = KafkaProducer(
        bootstrap_servers=KAFKA_BOOTSTRAP_SERVERS,
        value_serializer=lambda v: json.dumps(v).encode('utf-8'),
        retries=3,
        acks='all' # Ensure messages are acknowledged by all in-sync replicas
    )
    logger.info(f"Successfully connected to Kafka at {KAFKA_BOOTSTRAP_SERVERS}")
except KafkaError as e:
    logger.error(f"Failed to connect to Kafka: {e}")
    producer = None # Allow app to start but log error; endpoints using Kafka will fail

# --- FastAPI Application ---
app = FastAPI(
    title="AI-Driven Hybrid Cloud Management Platform - API Gateway",
    version="0.1.0",
    description="This is the central API gateway for the platform.",
)

# --- Dependencies (Example for future DB or Vault integration) ---
# async def get_db_session():
#     # Placeholder for database session management
#     pass

# async def get_vault_client():
#     # Placeholder for Vault client
#     pass


# --- API Endpoints ---
@app.get("/api/v1/health", response_model=HealthResponse, tags=["General"])
async def health_check():
    """
    Performs a health check of the API gateway.
    Returns the operational status of the service.
    """
    return HealthResponse(status="ok")

@app.post("/api/v1/auth/token", response_model=AuthTokenResponse, tags=["Authentication"])
async def login_for_access_token(form_data: AuthTokenRequest):
    """
    Placeholder for token generation.
    In a real implementation, this would validate credentials and issue a JWT.
    """
    # This is a mock implementation
    return AuthTokenResponse(access_token="fake-jwt-token", token_type="bearer")

@app.post("/api/v1/jobs", response_model=JobSubmissionResponse, status_code=202, tags=["Jobs"])
async def submit_job(payload: JobPayload):
    """
    Submits a new job to the orchestration tier via Kafka.
    The job payload is published to the 'tasks' Kafka topic.
    """
    if not producer:
        logger.error("Kafka producer not available. Cannot submit job.")
        raise HTTPException(status_code=503, detail="Job processing service is temporarily unavailable.")

    try:
        logger.info(f"Received job submission: {payload.dict()}")
        future = producer.send(KAFKA_TASKS_TOPIC, value=payload.dict())
        # Block for 'synchronous' send; consider async send in a real high-load scenario
        record_metadata = future.get(timeout=10)
        logger.info(f"Job '{payload.job_id}' sent to Kafka topic '{KAFKA_TASKS_TOPIC}' at offset {record_metadata.offset}")
        return JobSubmissionResponse(
            message="Job submitted successfully.",
            job_id=payload.job_id,
            kafka_offset=record_metadata.offset
        )
    except KafkaError as e:
        logger.error(f"Failed to send job '{payload.job_id}' to Kafka: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to submit job to processing queue: {e}")
    except Exception as e:
        logger.error(f"An unexpected error occurred while submitting job '{payload.job_id}': {e}")
        raise HTTPException(status_code=500, detail="An unexpected error occurred.")


@app.post("/api/v1/blueprints/{blueprint_id}/deploy", response_model=BlueprintDeploymentResponse, status_code=202, tags=["Blueprints"])
async def deploy_blueprint(blueprint_id: str, request_body: BlueprintDeploymentRequest):
    """
    Submits a blueprint deployment request to the orchestration tier via Kafka.
    The raw blueprint YAML is published to the 'blueprint.deployment.requested' Kafka topic.
    """
    if not producer:
        logger.error("Kafka producer not available. Cannot submit blueprint deployment.")
        raise HTTPException(status_code=503, detail="Blueprint deployment service is temporarily unavailable.")

    # The message to Kafka will include the blueprint_id from the path and the YAML from the body
    message_payload = {
        "blueprint_id": blueprint_id,
        "blueprint_yaml": request_body.blueprint_yaml
    }

    try:
        logger.info(f"Received blueprint deployment request for ID '{blueprint_id}'. Publishing to Kafka topic '{KAFKA_BLUEPRINT_DEPLOYMENT_TOPIC}'.")
        future = producer.send(KAFKA_BLUEPRINT_DEPLOYMENT_TOPIC, value=message_payload)
        record_metadata = future.get(timeout=10) # Synchronous send for simplicity

        logger.info(f"Blueprint deployment request for '{blueprint_id}' sent to Kafka. Offset: {record_metadata.offset}")
        return BlueprintDeploymentResponse(
            message="Blueprint deployment request submitted successfully.",
            blueprint_id=blueprint_id,
            kafka_topic=KAFKA_BLUEPRINT_DEPLOYMENT_TOPIC,
            kafka_offset=record_metadata.offset
        )
    except KafkaError as e:
        logger.error(f"Failed to send blueprint deployment request for '{blueprint_id}' to Kafka: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to submit blueprint for processing: {e}")
    except Exception as e:
        logger.error(f"An unexpected error occurred while submitting blueprint '{blueprint_id}': {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="An unexpected error occurred during blueprint submission.")


@app.post("/api/v1/incidents/test", response_model=TestIncidentResponse, status_code=202, tags=["Incidents"])
async def submit_test_incident(payload: Optional[TestIncidentPayload] = Body(None)):
    """
    Submits a sample incident to the 'incidents.detected' Kafka topic.
    This is used to test the remediation-service RAG workflow.
    If no payload is provided, a default test incident is used.
    """
    if not producer:
        logger.error("Kafka producer not available. Cannot submit test incident.")
        raise HTTPException(status_code=503, detail="Incident processing service is temporarily unavailable.")

    incident_payload = payload if payload else TestIncidentPayload()
    # Ensure all fields are present as expected by RemediationService's IncidentPayload model
    # The TestIncidentPayload model with defaults should handle this.

    try:
        logger.info(f"Received test incident submission: ID {incident_payload.incident_id}. Publishing to Kafka topic '{KAFKA_INCIDENTS_DETECTED_TOPIC}'.")
        # The TestIncidentPayload model should be compatible with RemediationService's IncidentPayload
        future = producer.send(KAFKA_INCIDENTS_DETECTED_TOPIC, value=incident_payload.dict(by_alias=True))
        record_metadata = future.get(timeout=10)

        logger.info(f"Test incident '{incident_payload.incident_id}' sent to Kafka. Offset: {record_metadata.offset}")
        return TestIncidentResponse(
            message="Test incident submitted successfully.",
            incident_id=incident_payload.incident_id,
            kafka_topic=KAFKA_INCIDENTS_DETECTED_TOPIC,
            kafka_offset=record_metadata.offset
        )
    except KafkaError as e:
        logger.error(f"Failed to send test incident '{incident_payload.incident_id}' to Kafka: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to submit test incident: {e}")
    except Exception as e:
        logger.error(f"An unexpected error occurred while submitting test incident '{incident_payload.incident_id}': {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="An unexpected error occurred during test incident submission.")


# --- Application Lifecycle (Optional for more complex setups) ---
 @app.on_event("startup")
async def startup_event():
    global producer # Moved to the top
    logger.info("API Gateway starting up...")
    if producer is None: # Attempt re-connect if initial connection failed
        try:
            global producer
            producer = KafkaProducer(
                bootstrap_servers=KAFKA_BOOTSTRAP_SERVERS,
                value_serializer=lambda v: json.dumps(v).encode('utf-8'),
                retries=3,
                acks='all'
            )
            logger.info(f"Kafka producer re-initialized successfully on startup.")
        except KafkaError as e:
            logger.error(f"Failed to re-initialize Kafka producer on startup: {e}")


@app.on_event("shutdown")
async def shutdown_event():
    logger.info("API Gateway shutting down...")
    if producer:
        producer.flush() # Ensure all pending messages are sent
        producer.close()
        logger.info("Kafka producer closed.")

if __name__ == "__main__":
    import uvicorn
    # This block is for direct execution (e.g., python main.py)
    # Uvicorn is typically run from the Docker CMD or a process manager like Gunicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
