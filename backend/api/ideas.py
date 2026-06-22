import uuid
from typing import Literal, Optional

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel

from pipelines.ideation import generate_ideas

router = APIRouter()


# ---------------------------------------------------------------------------
# Generate ideas
# ---------------------------------------------------------------------------

@router.post("/clients/{client_id}/ideas/generate")
async def generate_client_ideas(
    client_id: uuid.UUID,
    request: Request,
    n: int = Query(default=12, ge=1, le=50),
):
    pool = request.app.state.pool
    async with pool.acquire() as conn:
        try:
            return await generate_ideas(conn, client_id, n=n)
        except ValueError as e:
            raise HTTPException(status_code=404, detail=str(e))
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))


# ---------------------------------------------------------------------------
# List ideas — display-ready with joins + resolved proof points
# ---------------------------------------------------------------------------

@router.get("/clients/{client_id}/ideas")
async def list_client_ideas(
    client_id: uuid.UUID,
    request: Request,
    batch_id: Optional[uuid.UUID] = Query(default=None),
    status: Optional[str] = Query(default=None),
):
    pool = request.app.state.pool
    async with pool.acquire() as conn:
        where = ["i.client_id = $1"]
        params: list = [client_id]

        if batch_id is not None:
            params.append(batch_id)
            where.append(f"i.batch_id = ${len(params)}")
        if status is not None:
            params.append(status)
            where.append(f"i.status = ${len(params)}")

        rows = await conn.fetch(
            f"""
            SELECT
                i.id, i.batch_id, i.hook, i.creative_type, i.lead_type,
                i.score_impact, i.score_confidence, i.score_ease,
                i.score_reasoning, i.status, i.created_at,
                i.proof_point_ids, i.client_id,
                a.name        AS angle_name,
                av.description AS avatar_description,
                pp.pain        AS pain_addressed
            FROM ideas i
            LEFT JOIN angles      a  ON i.angle_id         = a.id
            LEFT JOIN avatars     av ON i.target_avatar_id  = av.id
            LEFT JOIN pain_points pp ON i.pain_point_id     = pp.id
            WHERE {" AND ".join(where)}
            ORDER BY i.created_at DESC
            """,
            *params,
        )

        # Batch-resolve all proof UUIDs in one query
        all_proof_ids = {
            pid
            for row in rows
            for pid in (row["proof_point_ids"] or [])
        }
        proof_map: dict[str, dict] = {}
        if all_proof_ids:
            proof_rows = await conn.fetch(
                "SELECT id, type, value FROM proof_bank WHERE id = ANY($1::uuid[])",
                list(all_proof_ids),
            )
            for p in proof_rows:
                proof_map[str(p["id"])] = {"type": p["type"], "value": p["value"]}

        ideas = []
        for row in rows:
            idea = dict(row)
            idea["id"] = str(idea["id"])
            idea["batch_id"] = str(idea["batch_id"]) if idea.get("batch_id") else None
            idea["client_id"] = str(idea["client_id"])
            idea["created_at"] = (
                idea["created_at"].isoformat() if idea["created_at"] else None
            )
            idea["proof_points"] = [
                proof_map[str(pid)]
                for pid in (row["proof_point_ids"] or [])
                if str(pid) in proof_map
            ]
            del idea["proof_point_ids"]
            ideas.append(idea)

        return ideas


# ---------------------------------------------------------------------------
# Idea stats — lightweight summary for the dashboard header
# ---------------------------------------------------------------------------

@router.get("/clients/{client_id}/ideas/stats")
async def get_ideas_stats(
    client_id: uuid.UUID,
    request: Request,
):
    pool = request.app.state.pool
    async with pool.acquire() as conn:
        idea_row = await conn.fetchrow(
            """
            SELECT
                COUNT(*)                                      AS total_ideas,
                COUNT(DISTINCT batch_id)                      AS total_batches,
                COUNT(*) FILTER (WHERE status = 'approved')   AS approved,
                COUNT(*) FILTER (WHERE status = 'rejected')   AS rejected,
                COUNT(*) FILTER (WHERE status = 'pending')    AS pending
            FROM ideas
            WHERE client_id = $1
            """,
            client_id,
        )

        script_row = await conn.fetchrow(
            """
            SELECT
                COUNT(*)                                    AS total_scripts,
                COUNT(*) FILTER (WHERE status = 'passed')  AS passed_scripts,
                COUNT(*) FILTER (WHERE status = 'failed')  AS failed_scripts
            FROM scripts
            WHERE client_id = $1
            """,
            client_id,
        )

        exemplar_count = await conn.fetchval(
            """
            SELECT COUNT(DISTINCT i.id)
            FROM ideas i
            JOIN scripts s ON s.idea_id = i.id
            WHERE i.client_id = $1
              AND i.status = 'approved'
              AND s.status = 'passed'
            """,
            client_id,
        )

        return {
            "total_ideas": int(idea_row["total_ideas"]),
            "total_batches": int(idea_row["total_batches"]),
            "by_status": {
                "approved": int(idea_row["approved"]),
                "rejected": int(idea_row["rejected"]),
                "pending": int(idea_row["pending"]),
            },
            "total_scripts": int(script_row["total_scripts"]),
            "passed_scripts": int(script_row["passed_scripts"]),
            "failed_scripts": int(script_row["failed_scripts"]),
            "approved_exemplars_count": int(exemplar_count),
        }


# ---------------------------------------------------------------------------
# Batches list — for the run filter tabs
# ---------------------------------------------------------------------------

@router.get("/clients/{client_id}/ideas/batches")
async def list_idea_batches(
    client_id: uuid.UUID,
    request: Request,
):
    pool = request.app.state.pool
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT
                ib.id,
                ib.created_at,
                COUNT(i.id) AS idea_count
            FROM idea_batches ib
            LEFT JOIN ideas i ON i.batch_id = ib.id
            WHERE ib.client_id = $1
            GROUP BY ib.id, ib.created_at
            ORDER BY ib.created_at ASC
            """,
            client_id,
        )
        return [
            {
                "id": str(r["id"]),
                "created_at": r["created_at"].isoformat() if r["created_at"] else None,
                "idea_count": int(r["idea_count"]),
            }
            for r in rows
        ]


# ---------------------------------------------------------------------------
# Approve / Reject — human gate; approved triggers async script generation
# ---------------------------------------------------------------------------

class StatusUpdate(BaseModel):
    status: Literal["approved", "rejected"]


@router.patch("/ideas/{idea_id}/status")
async def update_idea_status(
    idea_id: uuid.UUID,
    body: StatusUpdate,
    request: Request,
):
    pool = request.app.state.pool
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "UPDATE ideas SET status=$1 WHERE id=$2 RETURNING *",
            body.status,
            idea_id,
        )
        if not row:
            raise HTTPException(status_code=404, detail="Idea not found")

        if body.status == "approved":
            idea_data = {
                "id": str(row["id"]),
                "client_id": str(row["client_id"]),
                "hook": row["hook"],
                "creative_type": row["creative_type"],
                "lead_type": row["lead_type"],
                "status": row["status"],
                "score_impact": row["score_impact"],
                "score_confidence": row["score_confidence"],
                "score_ease": row["score_ease"],
                "score_reasoning": row["score_reasoning"],
                "angle_id": str(row["angle_id"]) if row["angle_id"] else None,
                "target_avatar_id": str(row["target_avatar_id"]) if row["target_avatar_id"] else None,
                "pain_point_id": str(row["pain_point_id"]) if row["pain_point_id"] else None,
                "proof_point_ids": [str(p) for p in (row["proof_point_ids"] or [])],
            }
            from tasks.script_tasks import generate_script_for_idea
            generate_script_for_idea.delay(idea_data)

        return {"id": str(idea_id), "status": body.status}
