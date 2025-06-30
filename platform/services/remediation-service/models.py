from pydantic import BaseModel, Field, conlist
from typing import List, Dict, Any, Optional, Union, Literal

# --- Input Models ---
class IncidentPayload(BaseModel):
    incident_id: str = Field(..., example="INC-2023-4578")
    title: str = Field(..., example="High CPU Utilization on Database Server")
    description: str = Field(..., example="The primary database server db-prod-01 is experiencing CPU utilization above 90% for the past 30 minutes.")
    priority: Optional[Literal["P1", "P2", "P3", "P4"]] = Field("P3", example="P1")
    affected_resources: List[Dict[str, Any]] = Field(default_factory=list, example=[{"type": "database", "id": "db-prod-01", "name": "Primary PostgreSQL"}])
    telemetry_data: Optional[Dict[str, Any]] = Field(default_factory=dict, example={"cpu_utilization": "92%", "active_queries": 250})
    additional_context: Optional[Dict[str, Any]] = Field(default_factory=dict)


# --- Output Models (Structured Executable Remediation Plan) ---
# Matches the schema from docs/phase-4-implementation-plan.md

class RetrievedContextItem(BaseModel):
    source_document_name: str = Field(..., example="db_high_cpu_runbook.md")
    chunk_id: str = Field(..., example="db_high_cpu_runbook.md-chunk_3")
    relevance_score: Optional[float] = Field(None, example=0.92)
    text_snippet: str = Field(..., example="Step 3: If high CPU is due to a specific query...")

class RemediationStepParameters(BaseModel):
    # Common across multiple action_types
    service_name: Optional[str] = Field(None, description="Internal or well-known external service name for api_call.")
    endpoint: Optional[str] = Field(None, description="The API endpoint path for api_call.")
    method: Optional[Literal["GET", "POST", "PUT", "DELETE", "PATCH"]] = Field(None, description="HTTP method for api_call.")
    payload: Optional[Union[Dict[str, Any], List[Any]]] = Field(None, description="JSON payload for POST/PUT/PATCH api_call or Kafka message.")
    headers: Optional[Dict[str, str]] = Field(None, description="HTTP headers for api_call or webhook.")

    target_host_selector: Optional[str] = Field(None, description="Selector for target host(s) for run_script/execute_command.")
    command_or_script_path: Optional[str] = Field(None, description="Command or script path for run_script/execute_command.")
    script_content_base64: Optional[str] = Field(None, description="Base64 encoded script content for run_script.")
    arguments: Optional[List[str]] = Field(default_factory=list, description="Arguments for run_script/execute_command.")
    timeout_seconds: Optional[int] = Field(300, description="Timeout for run_script/execute_command.")

    url: Optional[str] = Field(None, description="URL for webhook.")

    topic: Optional[str] = Field(None, description="Kafka topic for kafka_message.")
    key: Optional[str] = Field(None, description="Optional Kafka message key for kafka_message.")

    # Allows any other parameters, useful for custom action_types or future expansion
    class Config:
        extra = "allow"


class RemediationStep(BaseModel):
    step_number: int = Field(..., description="Sequential number of the remediation step.")
    title: str = Field(..., description="A short, human-readable title for the step.", example="Isolate Affected Database")
    description: str = Field(..., description="Detailed human-readable description of the action to be performed and its intent.")
    action_type: Literal[
        "api_call", "run_script", "execute_command", "manual_intervention", "webhook", "kafka_message"
    ] = Field(..., description="The type of action to be performed.")
    target_resource_id: Optional[str] = Field(None, description="Identifier of the primary resource this action targets.", example="vm-abcdef123456")
    parameters: RemediationStepParameters = Field(default_factory=RemediationStepParameters)
    expected_outcome: str = Field(..., description="A brief description of what success looks like for this step.")
    rollback_step_numbers: Optional[List[int]] = Field(default_factory=list, description="Optional: Step numbers for rolling back this action.")

class RemediationPlan(BaseModel):
    incident_id: str = Field(..., example="INC-2023-4578")
    confidence_score: Optional[float] = Field(None, ge=0.0, le=1.0, example=0.85, description="AI's confidence in the plan (0.0 to 1.0).")
    root_cause_analysis: str = Field(..., example="High CPU on db-prod-01 correlated with inefficient query from reporting-service.")
    retrieved_context: List[RetrievedContextItem] = Field(default_factory=list, description="Contextual information retrieved that informed the analysis.")
    remediation_plan: conlist(RemediationStep, min_items=1) # Must have at least one step

    class Config:
        schema_extra = {
            "example": {
                "incident_id": "INC-123",
                "confidence_score": 0.90,
                "root_cause_analysis": "Textual summary of the root cause based on RAG.",
                "retrieved_context": [
                    {
                        "source_document_name": "runbook_db_cpu.md",
                        "chunk_id": "runbook_db_cpu.md-chunk_2",
                        "relevance_score": 0.88,
                        "text_snippet": "If pg_stat_activity shows a long running query, consider terminating it using pg_terminate_backend(pid)."
                    }
                ],
                "remediation_plan": [
                    {
                        "step_number": 1,
                        "title": "Isolate Database Server",
                        "description": "Isolate the affected database server db-prod-01 from web traffic by applying a temporary firewall rule.",
                        "action_type": "api_call",
                        "target_resource_id": "db-prod-01",
                        "parameters": {
                            "service_name": "governance-engine", # Hypothetical internal service
                            "endpoint": "/v1/firewall/apply_rule",
                            "method": "POST",
                            "payload": {"ip_address": "10.1.2.3", "rule_id": "TEMP_DENY_WEB_TRAFFIC"}
                        },
                        "expected_outcome": "db-prod-01 is no longer accessible from application servers.",
                        "rollback_step_numbers": [101] # Example: step 101 to remove firewall rule
                    },
                    {
                        "step_number": 2,
                        "title": "Execute Diagnostic Script",
                        "description": "Execute diagnostic script 'find_long_running_query.sh' on db-prod-01 to identify the offending query.",
                        "action_type": "run_script",
                        "target_resource_id": "db-prod-01",
                        "parameters": {
                            "target_host_selector": "db-prod-01",
                            "command_or_script_path": "/opt/scripts/diagnostics/find_long_running_query.sh",
                            "arguments": ["--threshold=300s"]
                        },
                        "expected_outcome": "Script output identifies long-running queries or indicates none found."
                    },
                    {
                        "step_number": 3,
                        "title": "Create JIRA Ticket",
                        "description": "Create a ticket for the development team to investigate the offending query if found.",
                        "action_type": "webhook",
                        "parameters": {
                            "url": "https://jira.mycompany.com/api/v2/issue",
                            "method": "POST",
                            "payload": {"project": "APPDEV", "summary": "Offending query detected on db-prod-01", "description": "Details: output from find_long_running_query.sh...", "issuetype": "Bug"},
                            "headers": {"Authorization": "Bearer JIRA_API_TOKEN_FROM_VAULT"}
                        },
                        "expected_outcome": "JIRA ticket successfully created with link provided."
                    },
                    {
                        "step_number": 4,
                        "title": "Notify Operations Team",
                        "description": "Send a notification to the operations team Kafka topic about the actions taken.",
                        "action_type": "kafka_message",
                        "parameters": {
                            "topic": "ops.notifications",
                            "payload": {
                                "incident_id": "INC-123",
                                "message": "Automated remediation steps initiated for high CPU on db-prod-01. Firewall rule applied, diagnostic script run. JIRA ticket created.",
                                "severity": "HIGH"
                            }
                        },
                        "expected_outcome": "Message published to Kafka topic ops.notifications."
                    }
                ]
            }
        }
```
