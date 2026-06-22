import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "utils"))

from worker import celery_app
from pipelines.script_generation import (
    get_sync_connection,
    fetch_script_context,
    build_script_payload,
    SCRIPT_SYSTEM_PROMPT,
    save_script,
    update_script_status,
    run_quality_review,
    _get_gemini_service,
)


@celery_app.task(name="generate_script_for_idea")
def generate_script_for_idea(idea_data: dict):
    """Generate script → quality review → update status."""
    idea_id = idea_data["id"]
    client_id = idea_data["client_id"]

    print(f"[SCRIPT] Starting generation for idea {idea_id}, client {client_id}")

    conn = get_sync_connection()

    try:
        print("[SCRIPT] Fetching script context for client...")
        context = fetch_script_context(conn, client_id, idea_data)

        print("[SCRIPT] Calling Gemini for script generation...")
        payload = build_script_payload(context, idea_data)
        service = _get_gemini_service()
        script_content = service.generate_text(payload, SCRIPT_SYSTEM_PROMPT, temperature=1.0)

        print(f"[SCRIPT] Script saved, running quality review... ({len(script_content)} chars)")
        script_id = save_script(conn, idea_id, client_id, script_content)

        print("[SCRIPT] Running quality review...")
        review_result = run_quality_review(conn, script_id, script_content, context, idea_data)

        if review_result["passed"]:
            update_script_status(conn, script_id, "passed")
            print(f"[SCRIPT] Quality review complete: passed ({review_result['score']}/11)")

            # Embed the passing script for learning loop and future similarity search
            try:
                sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "utils"))
                from embeddings import get_embedding
                script_embedding = get_embedding(script_content[:8000])
                emb_str = "[" + ",".join(str(x) for x in script_embedding) + "]"
                conn.execute(
                    "UPDATE scripts SET embedding = %s WHERE id = %s",
                    (emb_str, str(script_id))
                )
                print(f"[SCRIPT] Script embedding stored")
            except Exception as e:
                print(f"[SCRIPT] WARNING: Script embedding failed: {e}")
        else:
            update_script_status(conn, script_id, "failed")
            print(f"[SCRIPT] Quality review complete: failed ({review_result['score']}/11)")

        conn.commit()
        return {
            "idea_id": idea_id,
            "script_id": str(script_id),
            "status": "passed" if review_result["passed"] else "failed",
            "review": review_result,
        }

    except Exception as e:
        conn.rollback()
        print(f"[SCRIPT] ERROR: {e}")
        try:
            save_script(conn, idea_id, client_id, f"GENERATION FAILED: {str(e)}", status="error")
            conn.commit()
        except Exception:
            pass
        raise

    finally:
        conn.close()
