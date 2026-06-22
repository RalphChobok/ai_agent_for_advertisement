import io
import json
import uuid
from datetime import date
from typing import Optional

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import StreamingResponse

router = APIRouter()


def _coerce_json_object(value) -> dict:
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            return {}
        return parsed if isinstance(parsed, dict) else {}
    return {}


def _normalize_quality_review(row) -> dict:
    feedback = _coerce_json_object(row["feedback"])
    raw_items = feedback.get("items")
    items = []

    for index, item in enumerate(raw_items or [], start=1):
        item_number = item.get("item_number") or item.get("number") or index
        criterion = (
            item.get("criterion")
            or item.get("item_name")
            or item.get("name")
            or f"Criterion {item_number}"
        )
        reasoning = item.get("reasoning") or item.get("reason") or item.get("notes") or ""
        items.append(
            {
                "criterion": criterion,
                "passed": bool(item.get("passed")),
                "reasoning": reasoning,
            }
        )

    passed_count = sum(1 for item in items if item["passed"])
    if not items and row["score"] is not None:
        passed_count = int(row["score"])

    overall_pass = row["passed"]
    if overall_pass is None and isinstance(feedback, dict):
        overall_pass = feedback.get("passed")

    return {
        "script_id": str(row["script_id"]),
        "overall_pass": bool(overall_pass),
        "passed_count": passed_count,
        "total_count": len(items),
        "items": items,
        "overall_notes": feedback.get("overall_notes") if isinstance(feedback, dict) else None,
    }


@router.get("/clients/{client_id}/scripts")
async def list_client_scripts(
    client_id: uuid.UUID,
    request: Request,
    status: Optional[str] = Query(default=None),
):
    pool = request.app.state.pool
    async with pool.acquire() as conn:
        params: list = [client_id]
        status_clause = ""
        if status:
            params.append(status)
            status_clause = f"AND s.status = ${len(params)}"

        rows = await conn.fetch(
            f"""
            SELECT
                s.id          AS script_id,
                s.content,
                s.status,
                s.created_at,
                i.id          AS idea_id,
                i.hook,
                i.creative_type,
                i.lead_type,
                i.score_impact,
                i.score_confidence,
                i.score_ease,
                i.score_reasoning,
                i.proof_point_ids,
                a.name        AS angle_name,
                av.description AS avatar_description,
                pp.pain        AS pain_addressed,
                qr.passed,
                qr.score      AS review_score,
                qr.feedback   AS review_feedback
            FROM scripts s
            JOIN ideas i      ON s.idea_id         = i.id
            LEFT JOIN angles  a  ON i.angle_id     = a.id
            LEFT JOIN avatars av ON i.target_avatar_id = av.id
            LEFT JOIN pain_points pp ON i.pain_point_id = pp.id
            LEFT JOIN quality_reviews qr ON qr.script_id = s.id
            WHERE s.client_id = $1 {status_clause}
            ORDER BY s.created_at DESC
            """,
            *params,
        )

        # Batch-resolve all proof UUIDs in one query
        all_proof_ids = {
            pid
            for row in rows
            for pid in (row["proof_point_ids"] or [])
        }
        proof_map: dict = {}
        if all_proof_ids:
            proof_rows = await conn.fetch(
                "SELECT id, type, value FROM proof_bank WHERE id = ANY($1::uuid[])",
                list(all_proof_ids),
            )
            for p in proof_rows:
                proof_map[str(p["id"])] = {"type": p["type"], "value": p["value"]}

        scripts = []
        for row in rows:
            s = dict(row)
            s["script_id"] = str(s["script_id"])
            s["idea_id"] = str(s["idea_id"])
            s["created_at"] = s["created_at"].isoformat() if s["created_at"] else None
            s["proof_points"] = [
                proof_map[str(pid)]
                for pid in (row["proof_point_ids"] or [])
                if str(pid) in proof_map
            ]
            s["review_feedback"] = _coerce_json_object(s["review_feedback"]) if s.get("review_feedback") else None
            del s["proof_point_ids"]
            scripts.append(s)

        return scripts


@router.get("/scripts/{script_id}/quality-review")
async def get_script_quality_review(
    script_id: uuid.UUID,
    request: Request,
):
    pool = request.app.state.pool
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT script_id, passed, score, feedback
            FROM quality_reviews
            WHERE script_id = $1
            ORDER BY created_at DESC
            LIMIT 1
            """,
            script_id,
        )

    if not row:
        raise HTTPException(status_code=404, detail="Quality review not found")

    return _normalize_quality_review(row)


@router.post("/clients/{client_id}/scripts/export-to-gdocs")
async def export_scripts_to_gdocs(
    client_id: uuid.UUID,
    request: Request,
):
    import logging
    import os

    pool = request.app.state.pool
    async with pool.acquire() as conn:
        client = await conn.fetchrow(
            "SELECT brand FROM clients WHERE id=$1", client_id
        )
        if not client:
            raise HTTPException(status_code=404, detail="Client not found")

        rows = await conn.fetch(
            """
            SELECT
                s.content,
                s.created_at,
                i.hook,
                i.creative_type,
                i.lead_type,
                i.score_impact,
                i.score_confidence,
                i.score_ease,
                a.name AS angle_name,
                qr.score AS review_score
            FROM scripts s
            JOIN ideas i     ON s.idea_id        = i.id
            LEFT JOIN angles a ON i.angle_id     = a.id
            LEFT JOIN quality_reviews qr ON qr.script_id = s.id
            WHERE s.client_id = $1 AND s.status = 'passed'
            ORDER BY s.created_at DESC
            """,
            client_id,
        )

        if not rows:
            raise HTTPException(status_code=404, detail="No passing scripts found for this client")

    brand = client["brand"] or "Client"
    today = date.today().isoformat()
    creds_path = os.path.join(
        os.path.dirname(__file__), "..", "config", "google-service-account.json"
    )

    if not os.path.exists(creds_path):
        logging.warning("Google service account credentials not found at %s — falling back to .docx", creds_path)
        # Fall back: return docx as a download
        docx_bytes = _build_docx(brand, list(rows))
        brand_safe = brand.replace(" ", "_")
        filename = f"scripts_{brand_safe}_{today}.docx"
        return StreamingResponse(
            io.BytesIO(docx_bytes),
            media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )

    try:
        from googleapiclient.discovery import build
        from googleapiclient.http import MediaInMemoryUpload
        from google.oauth2 import service_account

        SCOPES = ["https://www.googleapis.com/auth/drive.file"]
        creds = service_account.Credentials.from_service_account_file(
            creds_path, scopes=SCOPES
        )
        drive_service = build("drive", "v3", credentials=creds)

        html_content = _build_html(brand, today, list(rows))

        file_metadata = {
            "name": f"Scripts - {brand} - {today}",
            "mimeType": "application/vnd.google-apps.document",
        }
        media = MediaInMemoryUpload(
            html_content.encode("utf-8"),
            mimetype="text/html",
            resumable=True,
        )
        file = drive_service.files().create(
            body=file_metadata,
            media_body=media,
            fields="id,webViewLink",
        ).execute()

        drive_service.permissions().create(
            fileId=file["id"],
            body={"type": "anyone", "role": "reader"},
        ).execute()

        return {"url": file["webViewLink"]}

    except Exception as exc:
        logging.exception("Google Docs export failed: %s", exc)
        raise HTTPException(
            status_code=500,
            detail=f"Google Docs export failed: {exc}. Check service account credentials.",
        )


def _build_html(brand: str, today: str, rows: list) -> str:
    parts = [
        f"<html><body>",
        f"<h1>Scripts for {brand}</h1>",
        f"<p><em>Generated: {today}</em></p>",
        "<hr>",
    ]
    for row in rows:
        hook = (row["hook"] or "")[:80]
        angle = row["angle_name"] or ""
        ice = f"I{row['score_impact']} C{row['score_confidence']} E{row['score_ease']}"
        review_score = row["review_score"]

        parts.append(f"<h2>{hook}</h2>")
        parts.append(
            f"<p><strong>Angle: {angle} | Type: {row['creative_type']} | "
            f"Lead: {row['lead_type']} | ICE: {ice}</strong></p>"
        )

        content = row["content"] or ""
        content_html = []
        for line in content.split("\n"):
            stripped = line.strip()
            is_section = (
                stripped.isupper()
                and len(stripped) > 2
                and not stripped.startswith("-")
            )
            if is_section:
                content_html.append(f"<p><strong>{stripped}</strong></p>")
            elif stripped:
                content_html.append(f"<p>{stripped}</p>")
            else:
                content_html.append("<br>")
        parts.extend(content_html)

        if review_score is not None:
            parts.append(f"<p><em>Quality: {review_score}/11 passed</em></p>")

        parts.append("<hr>")

    parts.append("</body></html>")
    return "\n".join(parts)


@router.get("/clients/{client_id}/scripts/download")
async def download_scripts_docx(
    client_id: uuid.UUID,
    request: Request,
):
    pool = request.app.state.pool
    async with pool.acquire() as conn:
        client = await conn.fetchrow(
            "SELECT brand FROM clients WHERE id=$1", client_id
        )
        if not client:
            raise HTTPException(status_code=404, detail="Client not found")

        rows = await conn.fetch(
            """
            SELECT
                s.content,
                s.created_at,
                i.hook,
                i.creative_type,
                i.lead_type,
                i.score_impact,
                i.score_confidence,
                i.score_ease,
                a.name AS angle_name
            FROM scripts s
            JOIN ideas i     ON s.idea_id        = i.id
            LEFT JOIN angles a ON i.angle_id     = a.id
            WHERE s.client_id = $1 AND s.status = 'passed'
            ORDER BY s.created_at DESC
            """,
            client_id,
        )

        if not rows:
            raise HTTPException(status_code=404, detail="No passing scripts found for this client")

        docx_bytes = _build_docx(client["brand"] or "Client", list(rows))

        brand_safe = (client["brand"] or "client").replace(" ", "_")
        filename = f"scripts_{brand_safe}_{date.today().isoformat()}.docx"

        return StreamingResponse(
            io.BytesIO(docx_bytes),
            media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )


def _build_docx(brand: str, rows: list) -> bytes:
    from docx import Document
    from docx.shared import Pt
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    from docx.oxml.ns import qn
    from docx.oxml import OxmlElement

    doc = Document()

    # Title page
    title_para = doc.add_paragraph()
    title_para.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = title_para.add_run(f"Scripts for {brand}")
    run.bold = True
    run.font.size = Pt(24)

    date_para = doc.add_paragraph()
    date_para.alignment = WD_ALIGN_PARAGRAPH.CENTER
    date_para.add_run(f"Generated: {date.today().isoformat()}")

    doc.add_page_break()

    for idx, row in enumerate(rows):
        hook = (row["hook"] or "")[:80]
        angle = row["angle_name"] or ""

        # Script heading (idea hook)
        doc.add_heading(hook, level=1)

        # Angle / Type / Lead subheading
        meta_para = doc.add_paragraph()
        meta_para.add_run(
            f"Angle: {angle} | Type: {row['creative_type']} | Lead: {row['lead_type']}"
        ).bold = True

        # ICE subheading
        ice_para = doc.add_paragraph()
        ice_para.add_run(
            f"ICE: I{row['score_impact']} C{row['score_confidence']} E{row['score_ease']}"
        ).bold = True

        doc.add_paragraph()  # spacer

        # Script content — preserve line breaks and section structure
        content = row["content"] or ""
        for line in content.split("\n"):
            stripped = line.strip()
            # Treat SECTION LABELS in all-caps as sub-headings
            is_section_label = (
                stripped.isupper()
                and len(stripped) > 2
                and not stripped.startswith("-")
            )
            if is_section_label:
                p = doc.add_paragraph()
                p.add_run(stripped).bold = True
            else:
                p = doc.add_paragraph(line)
                p.paragraph_format.space_after = Pt(0)

        # Page break between scripts (not after the last)
        if idx < len(rows) - 1:
            doc.add_page_break()

    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()
