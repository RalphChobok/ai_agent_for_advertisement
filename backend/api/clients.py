import uuid

from fastapi import APIRouter, Request

router = APIRouter()


@router.get("/clients")
async def list_clients(request: Request):
    """Return all clients with aggregate idea/script counts."""
    pool = request.app.state.pool
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT
                c.id,
                c.name,
                c.brand,
                c.created_at,
                COUNT(DISTINCT i.id)  AS total_ideas,
                COUNT(DISTINCT s.id)  AS total_scripts
            FROM clients c
            LEFT JOIN ideas   i ON i.client_id = c.id
            LEFT JOIN scripts s ON s.client_id = c.id
            GROUP BY c.id, c.name, c.brand, c.created_at
            ORDER BY c.created_at DESC
            """,
        )
        return [
            {
                "id": str(r["id"]),
                "name": r["name"],
                "brand": r["brand"],
                "created_at": r["created_at"].isoformat() if r["created_at"] else None,
                "total_ideas": int(r["total_ideas"]),
                "total_scripts": int(r["total_scripts"]),
            }
            for r in rows
        ]
