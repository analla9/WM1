import os
import httpx
from fastapi import FastAPI, HTTPException, Body
from pydantic import BaseModel, Field
from typing import Any, Dict, List, Optional
import logging
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="Governance Engine",
    version="0.1.0",
    description="Evaluates deployment plans against OPA policies.",
)

# --- Configuration ---
OPA_URL = os.getenv("OPA_URL", "http://opa:8181") # Default OPA server address
# This data path assumes policies are loaded under a 'system.main' package in OPA.
# Adjust if your OPA policy package structure is different.
# Example: if policies are in cost.rego, security.rego, tagging.rego under 'system.main'
# then the query path might be /v1/data/system/main
OPA_DECISION_PATH = os.getenv("OPA_DECISION_PATH", "/v1/data/system/main/violations")
# Alternatively, if you have a single entrypoint rule like `allow` and `deny_reasons`
# OPA_DECISION_PATH = os.getenv("OPA_DECISION_PATH", "/v1/data/system/main")


# --- Pydantic Models ---
class EvaluationInput(BaseModel):
    # This model should represent the structure of the "deployment plan"
    # that your Rego policies expect as input.
    # For Phase 3, it's a generic JSON object.
    # In a real system, this would be a well-defined schema.
    # Example:
    # resources: List[Dict[str, Any]]
    # environment: str
    # project_tags: Dict[str, str]
    # user_roles: List[str]
    # For now, use a generic Dict
    plan_data: Dict[str, Any] = Field(..., description="The deployment plan data to evaluate.")

class ViolationDetail(BaseModel):
    policy_name: str # e.g., "cost_policy", "security_policy_s3_public_read"
    message: str
    details: Optional[Dict[str, Any]] = None # Additional context from policy

class EvaluationResponse(BaseModel):
    allow: bool
    violations: List[ViolationDetail] = Field(default_factory=list)


# --- HTTP Client for OPA ---
# Using a global client can be more efficient for multiple requests.
# Ensure proper lifecycle management if the app becomes more complex.
opa_client = httpx.AsyncClient(base_url=OPA_URL, timeout=10.0)

async def query_opa(input_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Queries the OPA server with the given input data.
    The input data should be structured as OPA expects, typically {"input": your_data}.
    """
    try:
        # OPA expects the data under an "input" key
        opa_query_payload = {"input": input_data}
        logger.info(f"Querying OPA at {OPA_URL}{OPA_DECISION_PATH} with payload: {opa_query_payload}")

        response = await opa_client.post(OPA_DECISION_PATH, json=opa_query_payload)
        response.raise_for_status() # Raise an exception for HTTP errors (4xx or 5xx)

        opa_result = response.json()
        logger.info(f"Received response from OPA: {opa_result}")
        return opa_result

    except httpx.HTTPStatusError as e:
        logger.error(f"HTTP error occurred while querying OPA: {e.response.status_code} - {e.response.text}")
        raise HTTPException(status_code=502, detail=f"Error communicating with OPA: {e.response.status_code} - {e.response.text}")
    except httpx.RequestError as e:
        logger.error(f"Request error occurred while querying OPA: {e}")
        raise HTTPException(status_code=503, detail=f"Unable to connect to OPA policy server: {e}")
    except Exception as e:
        logger.error(f"An unexpected error occurred during OPA query: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"An unexpected error occurred while processing policy evaluation: {str(e)}")


@app.post("/v1/evaluate", response_model=EvaluationResponse)
async def evaluate_plan(evaluation_input: EvaluationInput):
    """
    Evaluates a deployment plan against configured OPA policies.

    - Accepts a generic JSON object representing the deployment plan.
    - Queries the OPA (Open Policy Agent) server.
    - Returns `{"allow": true}` if compliant, or `{"allow": false, "violations": [...]}` if not.
    """
    logger.info(f"Received evaluation request for plan: {evaluation_input.plan_data}")

    opa_response = await query_opa(evaluation_input.plan_data)

    # Process OPA response. The structure of opa_response depends on your Rego policies
    # and the OPA_DECISION_PATH.
    #
    # Scenario 1: OPA_DECISION_PATH points to a rule that returns a list of violations.
    # E.g., policies define `violations[msg] { ... }` and path is `/v1/data/system/main/violations`
    # Then opa_response might be: `{"result": ["msg1", "msg2"]}` or `{"result": []}`
    #
    # Scenario 2: OPA_DECISION_PATH points to a package and you query for specific rules.
    # E.g., path is `/v1/data/system/main` and policies define `allow = false { deny[_] }`
    # and `deny[msg] { ... }`.
    # Then opa_response might be: `{"result": {"allow": false, "deny": ["msg1"]}}`

    # For this example, let's assume OPA_DECISION_PATH points to a rule or package
    # that directly returns a list of violation objects if any, or an empty list/undefined if none.
    # And that the 'result' key contains this list.

    # Example: if your policies are structured to return a list of violation objects under 'result'
    # violations_from_opa = opa_response.get("result", [])

    # Let's adapt to a common pattern: OPA path returns a list of violation messages directly.
    # If `OPA_DECISION_PATH` is `/v1/data/system/main/violations` and `violations` is a set of rules in Rego:
    # `violations[{"policy_name": "cost", "message": "Expensive instance"}] { ... }`
    # Then the result might be `{"result": [{"policy_name": "cost", "message": "..."}]}`

    raw_violations = opa_response.get("result", [])
    parsed_violations: List[ViolationDetail] = []

    if isinstance(raw_violations, list):
        for viol in raw_violations:
            if isinstance(viol, dict):
                parsed_violations.append(ViolationDetail(
                    policy_name=viol.get("policy_name", "unknown_policy"),
                    message=viol.get("message", "No message provided."),
                    details=viol.get("details")
                ))
            elif isinstance(viol, str): # If policies just return strings
                parsed_violations.append(ViolationDetail(policy_name="unknown_policy", message=viol))
            else:
                logger.warning(f"Unexpected violation format from OPA: {viol}")
    elif raw_violations is not None: # Handle cases where 'result' might not be a list if no violations
        logger.warning(f"OPA result for violations was not a list: {raw_violations}")


    if not parsed_violations:
        logger.info("Evaluation result: ALLOWED")
        return EvaluationResponse(allow=True, violations=[])
    else:
        logger.info(f"Evaluation result: DENIED. Violations: {parsed_violations}")
        return EvaluationResponse(allow=False, violations=parsed_violations)


@app.on_event("startup")
async def startup_event():
    logger.info("Governance Engine starting up...")
    # You can add a check here to see if OPA is accessible on startup
    try:
        await opa_client.get("/health") # OPA has a /health endpoint
        logger.info(f"Successfully connected to OPA at {OPA_URL}")
    except Exception as e:
        logger.warning(f"Could not connect to OPA at {OPA_URL} on startup: {e}. Ensure OPA is running and accessible.")

@app.on_event("shutdown")
async def shutdown_event():
    logger.info("Governance Engine shutting down...")
    await opa_client.aclose()
    logger.info("OPA client closed.")

# To run this service locally (for testing):
# if __name__ == "__main__":
#     import uvicorn
#     # Ensure OPA is running, e.g., docker run -p 8181:8181 openpolicyagent/opa run --server
#     uvicorn.run(app, host="0.0.0.0", port=8002) # Use a different port
