import yaml
from fastapi import FastAPI, HTTPException, Body
from pydantic import ValidationError
import logging

# Assuming models.py is in the same directory
from models import Blueprint

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="Blueprint Service",
    version="0.1.0",
    description="Parses and validates CMP Blueprints.",
)

@app.post("/v1/parse", response_model=Blueprint) # Return the parsed Blueprint model
async def parse_blueprint(
    # Using Body(..., media_type="application/x-yaml") would be ideal if FastAPI/Starlette fully supported it
    # for automatic parsing. For now, we accept raw text/plain or application/yaml and parse manually.
    blueprint_yaml: str = Body(..., media_type="application/yaml", description="Raw Blueprint YAML content")
):
    """
    Parses and validates the provided Blueprint YAML.

    - Accepts raw YAML string as input.
    - Validates against the defined Pydantic schema for Blueprints.
    - Returns the structured JSON representation of the blueprint if valid.
    - Returns a detailed error message if YAML is malformed or schema validation fails.
    """
    logger.info("Received request to /v1/parse")
    try:
        # Load YAML into a Python dictionary
        data = yaml.safe_load(blueprint_yaml)
        if not isinstance(data, dict):
            logger.error("Failed to parse YAML or parsed into non-dict type.")
            raise HTTPException(status_code=400, detail="Invalid YAML format: Could not parse into a dictionary.")
        logger.debug(f"Successfully parsed YAML into dict: {data}")

        # Handle 'from' keyword in dependencies for Pydantic model compatibility
        # Pydantic uses 'from_tier' as alias because 'from' is a Python keyword.
        if 'spec' in data and data['spec'] and 'dependencies' in data['spec'] and data['spec']['dependencies']:
            for dep_data in data['spec']['dependencies']:
                if 'from' in dep_data:
                    dep_data['from_tier'] = dep_data.pop('from')

        # Validate the dictionary against the Pydantic Blueprint model
        blueprint_obj = Blueprint(**data)
        logger.info(f"Blueprint '{blueprint_obj.metadata.name}' parsed and validated successfully.")

        # Return the Pydantic model, FastAPI will serialize it to JSON.
        # Use by_alias=True to ensure 'from' is used in output for dependencies.
        return blueprint_obj.dict(by_alias=True)

    except yaml.YAMLError as e:
        logger.error(f"YAML parsing error: {e}")
        raise HTTPException(status_code=400, detail=f"Invalid YAML content: {e}")
    except ValidationError as e:
        logger.error(f"Blueprint schema validation error: {e.errors()}")
        # Provide detailed validation errors
        raise HTTPException(status_code=422, detail={"message": "Blueprint validation failed.", "errors": e.errors()})
    except Exception as e:
        logger.error(f"Unexpected error during blueprint parsing: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"An unexpected error occurred: {str(e)}")

# To run this service locally (for testing, not for Docker usually):
# if __name__ == "__main__":
#     import uvicorn
#     uvicorn.run(app, host="0.0.0.0", port=8001) # Use a different port if api-gateway uses 8000
