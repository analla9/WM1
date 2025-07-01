import os
import json
import logging
import time
from kafka import KafkaConsumer
from kafka.errors import KafkaError
from dotenv import load_dotenv

# Load environment variables from .env file for local development consistency
load_dotenv()

import httpx # Added for Phase 3

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# --- Configuration ---
KAFKA_BOOTSTRAP_SERVERS = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "kafka:9092").split(',')
KAFKA_TASKS_TOPIC = "tasks"
KAFKA_DISCOVERY_TOPIC = "discovery.resource.updates"
KAFKA_BLUEPRINT_DEPLOYMENT_TOPIC = "blueprint.deployment.requested" # Added for Phase 3
KAFKA_CONSUMER_GROUP_ID = "orchestration-workers-group"

BLUEPRINT_SERVICE_URL = os.getenv("BLUEPRINT_SERVICE_URL", "http://blueprint-service:8000")
GOVERNANCE_ENGINE_URL = os.getenv("GOVERNANCE_ENGINE_URL", "http://governance-engine:8000")

# Attempt to import CanonicalCompute to verify shared models access
try:
    from platform.shared.models.compute import CanonicalCompute
    logger.info("Successfully imported CanonicalCompute from shared models.")
except ImportError as e:
    logger.error(f"Failed to import CanonicalCompute from shared models: {e}. Ensure PYTHONPATH is correctly set and models are available.")
    # Define a placeholder if import fails, to allow service to run, though with limited functionality.
    class CanonicalCompute: pass


async def call_blueprint_service(blueprint_yaml: str, blueprint_id: str):
    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            logger.info(f"Calling Blueprint Service ({BLUEPRINT_SERVICE_URL}/v1/parse) for blueprint ID: {blueprint_id}")
            response = await client.post(f"{BLUEPRINT_SERVICE_URL}/v1/parse", content=blueprint_yaml, headers={"Content-Type": "application/yaml"})
            response.raise_for_status()
            logger.info(f"Blueprint Service responded successfully for blueprint ID: {blueprint_id}")
            return response.json()
        except httpx.HTTPStatusError as e:
            logger.error(f"Blueprint Service returned an error for blueprint ID {blueprint_id}: {e.response.status_code} - {e.response.text}")
            return None
        except httpx.RequestError as e:
            logger.error(f"Request error while calling Blueprint Service for blueprint ID {blueprint_id}: {e}")
            return None

async def call_governance_engine(plan_data: dict, blueprint_id: str):
    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            logger.info(f"Calling Governance Engine ({GOVERNANCE_ENGINE_URL}/v1/evaluate) for blueprint ID: {blueprint_id}")
            payload = {"plan_data": plan_data} # Matches EvaluationInput model in governance-engine
            response = await client.post(f"{GOVERNANCE_ENGINE_URL}/v1/evaluate", json=payload)
            response.raise_for_status()
            logger.info(f"Governance Engine responded successfully for blueprint ID: {blueprint_id}")
            return response.json()
        except httpx.HTTPStatusError as e:
            logger.error(f"Governance Engine returned an error for blueprint ID {blueprint_id}: {e.response.status_code} - {e.response.text}")
            return None
        except httpx.RequestError as e:
            logger.error(f"Request error while calling Governance Engine for blueprint ID {blueprint_id}: {e}")
            return None

# Using asyncio for main function if we are doing async HTTP calls
import asyncio

async def process_blueprint_deployment_request(message_value):
    blueprint_id = message_value.get("blueprint_id", "unknown_id")
    blueprint_yaml = message_value.get("blueprint_yaml")

    if not blueprint_yaml:
        logger.error(f"No blueprint_yaml found in message for blueprint ID: {blueprint_id}")
        return

    logger.info(f"Processing blueprint deployment request for ID: {blueprint_id}")

    # 1. Call Blueprint Service
    parsed_blueprint = await call_blueprint_service(blueprint_yaml, blueprint_id)
    if not parsed_blueprint:
        logger.error(f"Halting deployment for blueprint {blueprint_id} due to parsing failure.")
        return

    logger.info(f"Blueprint {blueprint_id} parsed successfully: {parsed_blueprint.get('metadata', {}).get('name', 'N/A')}")

    # 2. Generate Mock Deployment Plan
    # This plan should be structured to test your Rego policies.
    # Example: a plan that might violate cost, security, and tagging policies.
    mock_plan = {
        "project_context": {"environment_type": "non-production"}, # For cost.rego
        "resources": [
            {
                "name": "web-server-expensive",
                "type": "aws_instance",
                "instance_type": "p5.48xlarge", # Violates cost.rego
                "tags": {"environment": "dev", "owner": "team-gamma"} # Has owner, but expensive
            },
            {
                "name": "public-s3-bucket",
                "type": "aws_s3_bucket",
                "properties": {"acl": "public-read"}, # Violates security.rego
                "tags": {"owner": "team-beta"} # Has owner
            },
            {
                "name": "resource-missing-owner-tag",
                "type": "aws_db_instance",
                "instance_type": "db.t3.micro",
                "tags": {"environment": "staging"} # Violates tagging.rego
            },
            {
                "name": "compliant-resource",
                "type": "aws_instance",
                "instance_type": "t3.micro",
                "tags": {"environment": "dev", "owner": "team-alpha"} # Compliant
            }
        ]
    }
    logger.info(f"Generated mock deployment plan for blueprint {blueprint_id}: {mock_plan}")

    # 3. Call Governance Engine
    governance_decision = await call_governance_engine(mock_plan, blueprint_id)
    if not governance_decision:
        logger.error(f"Halting deployment for blueprint {blueprint_id} due to governance evaluation failure.")
        return

    # 4. Log Decision
    if governance_decision.get("allow"):
        logger.info(f"Deployment Approved for blueprint ID: {blueprint_id}")
        # Proceed with actual deployment steps in future phases
    else:
        violations = governance_decision.get("violations", [])
        logger.warning(f"Deployment Denied for blueprint ID: {blueprint_id}. Violations: {violations}")


async def main_async(): # Renamed from main to main_async
    logger.info("Orchestration Worker starting...")
    logger.info(f"Attempting to connect to Kafka: {KAFKA_BOOTSTRAP_SERVERS}")
    subscribed_topics = [KAFKA_TASKS_TOPIC, KAFKA_DISCOVERY_TOPIC, KAFKA_BLUEPRINT_DEPLOYMENT_TOPIC]
    logger.info(f"Subscribing to topics: {subscribed_topics}")
    logger.info(f"Consumer group ID: {KAFKA_CONSUMER_GROUP_ID}")

    consumer = None
    retries = 0
    max_retries = 10 # Max retries for initial connection
    retry_delay = 10  # Seconds to wait between retries

    while retries < max_retries:
        try:
            consumer = KafkaConsumer(
                # KAFKA_TASKS_TOPIC, # Now subscribing to multiple topics
                *subscribed_topics, # Unpack the list of topics
                bootstrap_servers=KAFKA_BOOTSTRAP_SERVERS,
                auto_offset_reset='earliest', # Start reading at the earliest message if no offset is stored
                group_id=KAFKA_CONSUMER_GROUP_ID,
                value_deserializer=lambda v: json.loads(v.decode('utf-8')),
                # security_protocol='PLAINTEXT', # Explicitly set if needed, usually default
                # consumer_timeout_ms=1000 # Optional: if you want the consumer to time out if no messages
            )
            logger.info(f"Successfully connected to Kafka and subscribed to topics: {subscribed_topics}.")
            break # Exit retry loop on successful connection
        except KafkaError as e:
            retries += 1
            logger.error(f"Failed to connect to Kafka (attempt {retries}/{max_retries}): {e}")
            if retries >= max_retries:
                logger.error("Max retries reached. Exiting worker.")
                return # Exit if max retries are reached
            logger.info(f"Retrying in {retry_delay} seconds...")
            time.sleep(retry_delay)
        except Exception as e: # Catch other potential errors during setup
            logger.error(f"An unexpected error occurred during Kafka consumer setup: {e}")
            return # Exit on other critical errors

    if not consumer: # Should not happen if loop logic is correct, but as a safeguard
        logger.error("Consumer could not be initialized. Exiting.")
        return

    logger.info("Waiting for messages...")
    try:
        for message in consumer:
            # message value and key are raw bytes -- decode if necessary!
            # e.g., for JSON: message.value.decode('utf-8')
            logger.info(
                f"Received message from topic '{message.topic}' "
                f"(partition {message.partition}, offset {message.offset}):\n"
                f"Key: {message.key}\n"
                f"Value: {message.value}"
            )

            if message.topic == KAFKA_TASKS_TOPIC:
                logger.info(f"[{KAFKA_TASKS_TOPIC}] Processing task: {message.value.get('task_name', 'Unknown Task')}")
                # Add task processing logic here in future
            elif message.topic == KAFKA_DISCOVERY_TOPIC:
                logger.info(f"[{KAFKA_DISCOVERY_TOPIC}] Received resource update: {message.value.get('name', 'Unknown Resource')}")
                # Add resource update handling logic here in future
            elif message.topic == KAFKA_BLUEPRINT_DEPLOYMENT_TOPIC:
                logger.info(f"[{KAFKA_BLUEPRINT_DEPLOYMENT_TOPIC}] Received blueprint deployment request.")
                # Since process_blueprint_deployment_request is async, and KafkaConsumer is sync,
                # we need to run it in an event loop.
                # This is a common pattern when mixing sync Kafka consumption with async tasks.
                asyncio.run(process_blueprint_deployment_request(message.value))
            else:
                logger.warning(f"Received message from unknown topic: {message.topic}")

            # Committing offsets: KafkaConsumer with group_id handles this automatically
                # try:
                #     compute_resource = CanonicalCompute(**message.value)
                #     logger.info(f"Successfully parsed discovered resource: {compute_resource.provider_id}")
                # except Exception as parse_error:
                #     logger.error(f"Failed to parse discovered resource: {parse_error}")

            # Committing offsets: KafkaConsumer with group_id handles this automatically
            # if enable_auto_commit=True (default). If set to False, manual commit is needed.
            # consumer.commit() # Example of manual commit

    except KeyboardInterrupt:
        logger.info("Orchestration Worker shutting down (KeyboardInterrupt)...")
    except Exception as e:
        logger.error(f"An error occurred while consuming messages: {e}", exc_info=True)
    finally:
        if consumer:
            logger.info("Closing Kafka consumer.")
            consumer.close()
        logger.info("Orchestration Worker stopped.")

if __name__ == "__main__":
    # main() # Old synchronous main
    try:
        asyncio.run(main_async())
    except KeyboardInterrupt:
        logger.info("Orchestration Worker (Async) shutting down (KeyboardInterrupt)...")
    except Exception as e:
        logger.error(f"Critical error in Orchestration Worker (Async): {e}", exc_info=True)
    finally:
        logger.info("Orchestration Worker (Async) stopped.")
