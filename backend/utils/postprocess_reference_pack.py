import os
import logging
from dotenv import load_dotenv
from llm_call import GeminiService

# Configure logging for pipeline visibility
logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()

def read_system_prompt(file_path: str) -> str:
    """
    Reads the system instruction from a specified text file.
    """
    try:
        with open(file_path, "r", encoding="utf-8") as file:
            return file.read().strip()
    except FileNotFoundError as e:
        logger.error(f"System prompt file not found at: {file_path}")
        raise e
    except Exception as e:
        logger.error(f"Error reading system prompt file: {e}")
        raise e

def generate_pipeline_response(
    user_prompt: str, 
    prompt_file_path: str = None,
    temperature: float = 0.0
) -> str:
    """
    Pipeline function to initialize the service, load the prompt, and generate text.
    
    Args:
        user_prompt (str): The input text/data you want the model to process.
        prompt_file_path (str): Path to the system instruction text file.
        temperature (float): The creativity/randomness of the response.
        
    Returns:
        str: The generated response from the model.
    """
    # 1. Fetch the system instruction
    system_instruction = read_system_prompt(prompt_file_path)
    
    # 2. Fetch the model name from environment variables
    model_name = os.getenv("MODEL_NAME", "gemini-2.5-flash") # Added a fallback model
    
    # 3. Initialize the service
    try:
        gemini_service = GeminiService(model_name=model_name)
    except Exception as e:
        logger.error(f"Failed to initialize GeminiService: {e}")
        raise e

    # 4. Generate the response
    logger.info("Generating response from Gemini...")
    try:
        response = gemini_service.generate_text(
            prompt=user_prompt,
            system_instruction=system_instruction,
            temperature=temperature
        )
        logger.info("Response generated successfully.")
        return response
    except Exception as e:
        logger.error(f"Failed to generate text: {e}")
        raise e
