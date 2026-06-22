import os
import logging
from dotenv import load_dotenv
import google.generativeai as genai

# Load environment variables from the .env file
load_dotenv()

# Set up basic logging for the utility
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class GeminiService:
    def __init__(self, model_name="gemini-2.5-flash"):
        """
        Initializes the Gemini client. 
        Requires GEMINI_API_KEY to be set in your .env file.
        """
        # Store the model name to instantiate it later per request
        self.model_name = model_name
        
        # Read the key securely from the environment
        self.api_key = os.environ.get("GEMINI_API_KEY")
        
        if not self.api_key:
            logger.error("GEMINI_API_KEY is not set in the .env file.")
            raise ValueError("Missing Gemini API Key. Check your .env file.")
        
        # Configure the global genai library
        genai.configure(api_key=self.api_key)

    def generate_text(self, prompt, system_instruction=None, temperature=0, max_tokens=None):
        """
        Sends a standard text prompt to the Gemini API, with an optional dynamic system instruction.
        """
        try:
            # Instantiate the model here to apply the system instruction dynamically
            model = genai.GenerativeModel(
                model_name=self.model_name,
                system_instruction=system_instruction
            )

            # Set specific generation configurations
            config = genai.types.GenerationConfig(
                temperature=temperature,
                max_output_tokens=max_tokens,
            )
            
            response = model.generate_content(
                prompt,
                generation_config=config
            )
            return response.text
            
        except Exception as e:
            logger.error(f"Gemini API Error during text generation: {e}")
            raise e