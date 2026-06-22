import asyncio
import json
import os
import sys
import uuid
from decimal import Decimal

import asyncpg
from dotenv import load_dotenv

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "utils"))
from llm_call import GeminiService

load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))

DEDUP_THRESHOLD = float(os.getenv("DEDUP_SIMILARITY_THRESHOLD", "0.85"))

_PROMPTS_DIR = os.path.join(os.path.dirname(__file__), "..", "prompts")

def _load_prompt(filename: str) -> str:
    with open(os.path.join(_PROMPTS_DIR, filename), "r", encoding="utf-8") as f:
        return f.read().strip()

SYSTEM_PROMPT = _load_prompt("ideation.txt")


def _row(record) -> dict:
    """Convert asyncpg Record to plain dict; UUIDs → str, Decimals → float."""
    out = {}
    for k, v in dict(record).items():
        if isinstance(v, uuid.UUID):
            out[k] = str(v)
        elif isinstance(v, Decimal):
            out[k] = float(v)
        else:
            out[k] = v
    return out


# ---------------------------------------------------------------------------
# Context fetchers
# ---------------------------------------------------------------------------

async def fetch_ideation_context(conn: asyncpg.Connection, client_id: uuid.UUID) -> dict:
    client = await conn.fetchrow(
        "SELECT name, brand, tone, voice_description, market_stage, core_emotion "
        "FROM clients WHERE id=$1",
        client_id,
    )
    if not client:
        raise ValueError(f"Client {client_id} not found")

    offers = await conn.fetch(
        "SELECT id, name, type, price, description FROM offers WHERE client_id=$1",
        client_id,
    )
    mechanisms = await conn.fetch(
        "SELECT name, description FROM mechanisms WHERE client_id=$1",
        client_id,
    )
    avatar_rows = await conn.fetch(
        "SELECT id, description, age_range, awareness_level, dominant_belief, key_phrase "
        "FROM avatars WHERE client_id=$1",
        client_id,
    )

    avatar_ids = [r["id"] for r in avatar_rows]
    pain_rows = (
        await conn.fetch(
            "SELECT id, avatar_id, pain FROM pain_points WHERE avatar_id = ANY($1::uuid[])",
            avatar_ids,
        )
        if avatar_ids
        else []
    )

    pains_by_avatar: dict[str, list] = {}
    for p in pain_rows:
        key = str(p["avatar_id"])
        pains_by_avatar.setdefault(key, []).append({"id": str(p["id"]), "pain": p["pain"]})

    audience = []
    for av in avatar_rows:
        aid = str(av["id"])
        entry = _row(av)
        entry["pains"] = pains_by_avatar.get(aid, [])
        audience.append(entry)

    angles = await conn.fetch(
        "SELECT id, name, description FROM angles WHERE client_id=$1",
        client_id,
    )
    proof = await conn.fetch(
        "SELECT id, type, value, source FROM proof_bank "
        "WHERE client_id=$1 AND is_verified=TRUE",
        client_id,
    )
    hook_rows = await conn.fetch(
        "SELECT id, type, content FROM hooks WHERE client_id=$1",
        client_id,
    )

    hook_inspiration: dict[str, list] = {}
    for h in hook_rows:
        hook_inspiration.setdefault(h["type"], []).append(
            {"id": str(h["id"]), "content": h["content"]}
        )

    rules = await conn.fetch(
        "SELECT type, rule FROM constraints WHERE client_id=$1",
        client_id,
    )
    creative_type_rows = await conn.fetch(
        "SELECT name FROM creative_types WHERE client_id=$1 ORDER BY name",
        client_id,
    )
    lead_type_rows = await conn.fetch(
        "SELECT name FROM lead_types WHERE client_id=$1 ORDER BY name",
        client_id,
    )

    approved_exemplars = await fetch_approved_exemplars(conn, client_id)

    return {
        "client": _row(client),
        "offers": [_row(r) for r in offers],
        "mechanisms": [_row(r) for r in mechanisms],
        "audience": audience,
        "allowed_angles": [_row(r) for r in angles],
        "allowed_proof": [_row(r) for r in proof],
        "hook_inspiration": hook_inspiration,
        "hard_rules": [dict(r) for r in rules],
        "allowed_creative_types": [r["name"] for r in creative_type_rows],
        "allowed_lead_types": [r["name"] for r in lead_type_rows],
        "approved_exemplars": approved_exemplars,
    }


async def fetch_already_generated(
    conn: asyncpg.Connection, client_id: uuid.UUID, limit: int = 200
) -> list:
    rows = await conn.fetch(
        """
        SELECT i.hook, ag.name AS angle, av.description AS avatar, i.creative_type
        FROM ideas i
        LEFT JOIN angles  ag ON i.angle_id        = ag.id
        LEFT JOIN avatars av ON i.target_avatar_id = av.id
        WHERE i.client_id = $1
        ORDER BY i.created_at DESC
        LIMIT $2
        """,
        client_id,
        limit,
    )
    return [dict(r) for r in rows]


async def fetch_approved_exemplars(
    conn: asyncpg.Connection, client_id: uuid.UUID, limit: int = 5
) -> list:
    """Fetch top-scoring ideas that were approved and whose scripts passed quality review."""
    rows = await conn.fetch(
        """
        SELECT i.hook, i.creative_type, i.lead_type,
               i.score_impact, i.score_confidence, i.score_ease,
               i.score_reasoning,
               a.name  AS angle_name,
               av.description AS avatar_description,
               pp.pain AS pain,
               s.content AS script_content
        FROM ideas i
        JOIN scripts s ON s.idea_id = i.id
        LEFT JOIN angles a       ON i.angle_id        = a.id
        LEFT JOIN avatars av     ON i.target_avatar_id = av.id
        LEFT JOIN pain_points pp ON i.pain_point_id    = pp.id
        WHERE i.client_id = $1
          AND i.status = 'approved'
          AND s.status = 'passed'
        ORDER BY i.score_impact + i.score_confidence + i.score_ease DESC
        LIMIT $2
        """,
        client_id,
        limit,
    )
    return [dict(r) for r in rows]


# ---------------------------------------------------------------------------
# Similarity search (embedding dedup)
# ---------------------------------------------------------------------------

async def find_similar_existing_ideas(
    conn: asyncpg.Connection,
    client_id: uuid.UUID,
    query_embedding: list[float],
    threshold: float = DEDUP_THRESHOLD,
) -> list:
    """Return existing ideas whose cosine similarity to query_embedding exceeds threshold."""
    embedding_str = "[" + ",".join(str(x) for x in query_embedding) + "]"
    similar = await conn.fetch(
        """
        SELECT id, hook, status,
               1 - (embedding <=> $1::vector) AS similarity
        FROM ideas
        WHERE client_id = $2
          AND embedding IS NOT NULL
          AND 1 - (embedding <=> $1::vector) > $3
        ORDER BY similarity DESC
        LIMIT 3
        """,
        embedding_str,
        client_id,
        threshold,
    )
    return [dict(r) for r in similar]


async def find_closest_existing_idea(
    conn: asyncpg.Connection,
    client_id: uuid.UUID,
    embedding_str: str,
) -> dict | None:
    """Return the single closest existing idea regardless of threshold.
    Used to populate the dedup_report for ALL ideas, not just rejected ones.
    """
    row = await conn.fetchrow(
        """
        SELECT id, hook,
               1 - (embedding <=> $1::vector) AS similarity
        FROM ideas
        WHERE client_id = $2
          AND embedding IS NOT NULL
        ORDER BY embedding <=> $1::vector
        LIMIT 1
        """,
        embedding_str,
        client_id,
    )
    return dict(row) if row else None


# ---------------------------------------------------------------------------
# Payload builder
# ---------------------------------------------------------------------------

def build_user_payload(context: dict, n: int, already_generated: list) -> str:
    def j(obj):
        return json.dumps(obj, ensure_ascii=False, indent=2)

    parts = [
        f"N = {n}",
        "=== CLIENT ===",
        j(context["client"]),
        "=== OFFERS ===",
        j(context["offers"]),
        "=== MECHANISMS ===",
        j(context["mechanisms"]),
        "=== HARD_RULES ===",
        j(context["hard_rules"]),
        "=== AUDIENCE ===",
        j(context["audience"]),
        "=== ALLOWED_ANGLES ===",
        j(context["allowed_angles"]),
        "=== ALLOWED_PROOF ===",
        j(context["allowed_proof"]),
        "=== ALLOWED_CREATIVE_TYPES ===",
        j(context["allowed_creative_types"]),
        "=== ALLOWED_LEAD_TYPES ===",
        j(context["allowed_lead_types"]),
        "=== HOOK_INSPIRATION (inspiration only, do not copy verbatim) ===",
        j(context["hook_inspiration"]),
        "=== ALREADY_GENERATED ===",
        j(already_generated),
    ]

    exemplars = context.get("approved_exemplars", [])
    if exemplars:
        winner_lines = [
            "\n=== APPROVED_WINNERS (learn from these — they passed quality review) ===",
            "These ideas were approved by the human reviewer AND their scripts passed the "
            "10-point quality gate. Generate ideas of EQUAL or HIGHER quality. "
            "Do NOT copy them — use them to understand what works.\n",
        ]
        for i, ex in enumerate(exemplars, 1):
            winner_lines.append(f"Winner #{i}:")
            winner_lines.append(f"  Hook: {ex['hook']}")
            winner_lines.append(f"  Angle: {ex['angle_name']}")
            winner_lines.append(f"  Type: {ex['creative_type']}, Lead: {ex['lead_type']}")
            winner_lines.append(f"  Avatar: {ex.get('avatar_description', 'N/A')}")
            winner_lines.append(f"  Pain: {ex.get('pain', 'N/A')}")
            winner_lines.append(
                f"  ICE: I{ex['score_impact']} C{ex['score_confidence']} E{ex['score_ease']}"
            )
            winner_lines.append(f"  Why it scored well: {ex['score_reasoning']}")
            if ex.get("script_content"):
                snippet = ex["script_content"][:300].replace("\n", " ")
                winner_lines.append(f"  Script snippet: {snippet}...")
            winner_lines.append("")
        parts.append("\n".join(winner_lines))

    return "\n\n".join(parts)


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

def _validate_ideas(ideas: list, context: dict) -> tuple[list, list]:
    allowed_angle_ids = {a["id"] for a in context["allowed_angles"]}
    allowed_avatar_ids = {a["id"] for a in context["audience"]}
    allowed_proof_ids = {p["id"] for p in context["allowed_proof"]}
    allowed_creative_types = set(context["allowed_creative_types"])
    pains_by_avatar: dict[str, set] = {
        a["id"]: {p["id"] for p in a.get("pains", [])}
        for a in context["audience"]
    }

    valid, rejected = [], []
    for idea in ideas:
        reasons = []

        if idea.get("angle_id") not in allowed_angle_ids:
            reasons.append(f"angle_id {idea.get('angle_id')!r} not in ALLOWED_ANGLES")

        avatar_id = idea.get("target_avatar_id")
        if avatar_id not in allowed_avatar_ids:
            reasons.append(f"target_avatar_id {avatar_id!r} not in AUDIENCE")
        else:
            pain_id = idea.get("pain_point_id")
            if pain_id and pain_id not in pains_by_avatar.get(avatar_id, set()):
                reasons.append(
                    f"pain_point_id {pain_id!r} does not belong to avatar {avatar_id!r}"
                )

        for pid in idea.get("proof_point_ids") or []:
            if pid not in allowed_proof_ids:
                reasons.append(f"proof_point_id {pid!r} not in ALLOWED_PROOF")

        if idea.get("creative_type") not in allowed_creative_types:
            reasons.append(f"creative_type {idea.get('creative_type')!r} not valid")

        if idea.get("lead_type") not in set(context["allowed_lead_types"]):
            reasons.append(f"lead_type {idea.get('lead_type')!r} not valid")

        for field in ("score_impact", "score_confidence", "score_ease"):
            val = idea.get(field)
            if not isinstance(val, int) or not (0 <= val <= 10):
                reasons.append(f"{field}={val!r} must be int 0–10")

        if reasons:
            rejected.append({"hook": idea.get("hook", "<no hook>"), "reasons": reasons})
        else:
            valid.append(idea)

    return valid, rejected


# ---------------------------------------------------------------------------
# LLM call (sync → thread)
# ---------------------------------------------------------------------------

async def _call_gemini(payload: str) -> str:
    model = os.getenv("IDEATION_MODEL", os.getenv("MODEL_NAME", "gemini-2.5-pro"))
    service = GeminiService(model_name=model)
    return await asyncio.to_thread(
        service.generate_text,
        payload,
        SYSTEM_PROMPT,
        1.0,
    )


def _parse_response(raw: str) -> list:
    text = raw.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1] if "\n" in text else text[3:]
        if text.endswith("```"):
            text = text[:-3]
    return json.loads(text.strip())


# ---------------------------------------------------------------------------
# Persistence
# ---------------------------------------------------------------------------

async def _persist_batch(
    conn: asyncpg.Connection,
    batch_id: uuid.UUID,
    client_id: uuid.UUID,
    ideas: list,
) -> list[dict]:
    inserted = []
    async with conn.transaction():
        for idea in ideas:
            idea_id = uuid.uuid4()
            await conn.execute(
                """
                INSERT INTO ideas (
                    id, client_id, batch_id, hook, angle_id, lead_type,
                    creative_type, target_avatar_id, pain_point_id,
                    proof_point_ids, score_impact, score_confidence,
                    score_ease, score_reasoning, status
                ) VALUES (
                    $1, $2, $3, $4, $5, $6,
                    $7, $8, $9,
                    $10, $11, $12,
                    $13, $14, $15
                )
                """,
                idea_id,
                client_id,
                batch_id,
                idea.get("hook"),
                uuid.UUID(idea["angle_id"]),
                idea.get("lead_type"),
                idea.get("creative_type"),
                uuid.UUID(idea["target_avatar_id"]),
                uuid.UUID(idea["pain_point_id"]) if idea.get("pain_point_id") else None,
                [uuid.UUID(p) for p in (idea.get("proof_point_ids") or [])],
                idea["score_impact"],
                idea["score_confidence"],
                idea["score_ease"],
                idea.get("score_reasoning"),
                "pending",
            )
            inserted.append({"id": str(idea_id), **idea})
    return inserted


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------

async def generate_ideas(
    conn: asyncpg.Connection, client_id: uuid.UUID, n: int = 12
) -> dict:
    # 1. Create batch record
    batch_id = uuid.uuid4()
    await conn.execute(
        "INSERT INTO idea_batches (id, client_id) VALUES ($1, $2)",
        batch_id,
        client_id,
    )

    # 2. Fetch context and memory (includes approved exemplars for learning loop)
    context = await fetch_ideation_context(conn, client_id)
    prior = await fetch_already_generated(conn, client_id)

    # 3. First LLM call
    payload = build_user_payload(context, n, prior)
    raw = await _call_gemini(payload)

    # 4. Parse + validate
    ideas = _parse_response(raw)
    valid, rejected = _validate_ideas(ideas, context)

    # 5. Single repair retry if >30% dropped
    if rejected and len(rejected) > 0.3 * len(ideas):
        repair_payload = (
            payload
            + "\n\n=== REPAIR REQUEST ===\n"
            + "The following concepts were rejected. Produce fresh replacements only — "
            "do not repeat any hook from ALREADY_GENERATED or the rejected list.\n"
            + json.dumps(rejected, ensure_ascii=False, indent=2)
        )
        raw2 = await _call_gemini(repair_payload)
        ideas2 = _parse_response(raw2)
        valid2, rejected2 = _validate_ideas(ideas2, context)

        seen = {v["hook"] for v in valid}
        for idea in valid2:
            if idea["hook"] not in seen:
                valid.append(idea)
                seen.add(idea["hook"])
        rejected = rejected + rejected2

    # 6. Embedding dedup: batch-embed all valid ideas, then filter near-duplicates
    dedup_rejected: list[dict] = []
    dedup_report: list[dict] = []
    ideas_to_persist = valid
    embeddings_to_store: list[list[float]] | None = None

    try:
        from embeddings import get_embeddings_batch, idea_to_embed_text

        embed_texts = [idea_to_embed_text(idea) for idea in valid]
        all_embeddings = get_embeddings_batch(embed_texts)

        deduplicated = []
        dedup_embeddings = []
        for idea, emb in zip(valid, all_embeddings):
            emb_str = "[" + ",".join(str(x) for x in emb) + "]"
            closest = await find_closest_existing_idea(conn, client_id, emb_str)

            sim = round(float(closest["similarity"]), 4) if closest else 0.0
            is_rejected = closest is not None and sim > DEDUP_THRESHOLD

            dedup_report.append({
                "idea_hook": idea["hook"],
                "closest_match_hook": closest["hook"] if closest else None,
                "closest_match_id": str(closest["id"]) if closest else None,
                "similarity_score": sim,
                "threshold": DEDUP_THRESHOLD,
                "status": "rejected" if is_rejected else "kept",
            })

            if is_rejected:
                dedup_rejected.append({
                    "hook": idea["hook"],
                    "reason": "Too similar to existing idea",
                    "similar_to": closest["hook"],
                    "similarity": round(sim, 3),
                })
            else:
                deduplicated.append(idea)
                dedup_embeddings.append(emb)

        ideas_to_persist = deduplicated
        embeddings_to_store = dedup_embeddings
        print(f"  Dedup: {len(dedup_rejected)} rejected, {len(deduplicated)} kept")

    except Exception as e:
        print(f"  WARNING: Embedding/dedup failed, skipping dedup: {e}")
        dedup_report = []

    # 7. Persist
    inserted = await _persist_batch(conn, batch_id, client_id, ideas_to_persist)

    # 8. Store embeddings for persisted ideas (reuse from step 6 — no extra API call)
    if embeddings_to_store is not None:
        try:
            for idea_record, emb in zip(inserted, embeddings_to_store):
                emb_str = "[" + ",".join(str(x) for x in emb) + "]"
                await conn.execute(
                    "UPDATE ideas SET embedding = $1 WHERE id = $2",
                    emb_str,
                    uuid.UUID(idea_record["id"]),
                )
            print(f"  Embedded {len(inserted)} ideas")
        except Exception as e:
            print(f"  WARNING: Storing embeddings failed: {e}")

    # Batch number = total batches for this client (current batch already inserted)
    batch_number = await conn.fetchval(
        "SELECT COUNT(*) FROM idea_batches WHERE client_id = $1",
        client_id,
    )

    return {
        "batch_id": str(batch_id),
        "batch_number": int(batch_number),
        "generated": len(inserted),
        "rejected": rejected,
        "dedup_rejected": dedup_rejected,
        "dedup_report": dedup_report,
        "stats": {
            "total_generated": len(valid),
            "kept": len(inserted),
            "rejected_dedup": len(dedup_rejected),
        },
        "learning_context": {
            "exemplars_used": len(context.get("approved_exemplars", [])),
            "previous_ideas_checked": len(prior),
        },
        "ideas": inserted,
    }
