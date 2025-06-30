import os
import json
import logging
import time
from kafka import KafkaConsumer
from kafka.errors import KafkaError
from dotenv import load_dotenv

# Load environment variables from .env file for local development consistency
load_dotenv()

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# --- Configuration ---
KAFKA_BOOTSTRAP_SERVERS = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "kafka:9092").split(',') # Allow comma-separated list
KAFKA_TASKS_TOPIC = "tasks"
KAFKA_DISCOVERY_TOPIC = "discovery.resource.updates"
KAFKA_CONSUMER_GROUP_ID = "orchestration-workers-group" # Define a consumer group

# Attempt to import CanonicalCompute to verify shared models access
try:
    from platform.shared.models.compute import CanonicalCompute
    logger.info("Successfully imported CanonicalCompute from shared models.")
except ImportError as e:
    logger.error(f"Failed to import CanonicalCompute from shared models: {e}. Ensure PYTHONPATH is correctly set and models are available.")
    # Define a placeholder if import fails, to allow service to run, though with limited functionality.
    class CanonicalCompute: pass


def main():
    logger.info("Orchestration Worker starting...")
    logger.info(f"Attempting to connect to Kafka: {KAFKA_BOOTSTRAP_SERVERS}")
    subscribed_topics = [KAFKA_TASKS_TOPIC, KAFKA_DISCOVERY_TOPIC]
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
                logger.info(f"[Tasks Topic] Processing task: {message.value.get('task_name', 'Unknown Task')}")
                # Add task processing logic here in future
            elif message.topic == KAFKA_DISCOVERY_TOPIC:
                logger.info(f"[Discovery Topic] Received resource update: {message.value.get('name', 'Unknown Resource')}")
                # Add resource update handling logic here in future
                # For now, just logging is fine as per Phase 2 requirements.
                # Example: Could try to parse with CanonicalCompute if it's available
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
    main()
