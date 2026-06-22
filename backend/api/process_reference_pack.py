import os
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "utils"))

from fastapi import APIRouter, HTTPException, UploadFile, File
from liteparse import LiteParse
from llm_call import GeminiService
from save_postprocessed_reference import DatabaseInsertionStep

router = APIRouter()

PROMPTS_DIR = os.path.join(os.path.dirname(__file__), "..", "prompts")
DEFAULT_SYSTEM_PROMPT = os.path.join(PROMPTS_DIR, "reference_pack_extraction.txt")


@router.post("/process-reference-pack")
async def process_reference_pack(file: UploadFile = File(...)):
    print(f"\n[process-reference-pack] Received file: {file.filename} ({file.content_type})")

    # Step 1: Read the system prompt
    system_prompt_path = os.getenv("SYSTEM_PROMPT_PATH", DEFAULT_SYSTEM_PROMPT)
    try:
        with open(system_prompt_path, "r", encoding="utf-8") as f:
            system_prompt = f.read().strip()
        print(f"[process-reference-pack] Loaded system prompt from: {system_prompt_path}")
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"System prompt file not found: {system_prompt_path}")
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to read system prompt file: {e}")

    # Step 2: Save uploaded file to a temp path and parse it
    suffix = os.path.splitext(file.filename or "upload")[1] or ".pdf"
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
            content = await file.read()
            tmp.write(content)
            tmp_path = tmp.name
        print(f"[process-reference-pack] Saved to temp file: {tmp_path} ({len(content)} bytes)")

        parser = LiteParse()
        parsed = parser.parse(tmp_path)
        document_text = parsed.text
        print(f"[process-reference-pack] Parsed document — {len(document_text)} chars extracted")
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to parse file: {e}")
    finally:
        try:
            os.unlink(tmp_path)
        except Exception:
            pass

    # Step 3: Postprocess with LLM
    try:
        model_name = os.getenv("MODEL_NAME", "gemini-2.5-flash")
        print(f"[process-reference-pack] Calling LLM ({model_name})...")
        gemini_service = GeminiService(model_name=model_name)
        llm_response = gemini_service.generate_text(
            prompt=document_text,
            system_instruction=system_prompt,
            temperature=0.0,
        )
        print(f"[process-reference-pack] LLM responded — {len(llm_response)} chars")
    except ValueError as e:
        raise HTTPException(status_code=500, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"LLM processing failed: {e}")

    # Step 4: Parse JSON and save to the database
    try:
        print("[process-reference-pack] Inserting into database...")
        insertion_step = DatabaseInsertionStep(response=llm_response)
        results = insertion_step.run()
        print(f"[process-reference-pack] Done — inserted: {results}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Database insertion failed: {e}")

    client_ids = results.pop("_client_ids", [])
    return {"status": "success", "inserted": results, "client_ids": client_ids}
