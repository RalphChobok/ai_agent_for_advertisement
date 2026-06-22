import json
import os
import uuid
from decimal import Decimal

import psycopg2
import psycopg2.extras
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))

# Lazy import to avoid circular dependency at module level
def _get_gemini_service():
    import sys
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "utils"))
    from llm_call import GeminiService
    model_name = os.getenv("MODEL_NAME", "gemini-2.5-flash")
    return GeminiService(model_name=model_name)


# ---------------------------------------------------------------------------
# Three losing-script examples embedded as a constant (no DB table exists)
# ---------------------------------------------------------------------------

NEGATIVE_EXAMPLES = """
NEGATIVE EXAMPLE 1 — hype/guru energy (never emulate):
"Are you tired of working 9 to 5? I was too, until I discovered this secret method that made
me $10,000 in my first week! Now I live the laptop lifestyle and you can too! Click below to
join thousands of successful entrepreneurs who have transformed their lives..."

NEGATIVE EXAMPLE 2 — fake urgency / income claims (never emulate):
"STOP what you're doing! This SHOCKING secret the gurus don't want you to know is about to
change your life FOREVER! Limited spots — this offer expires in 10 minutes! I went from BROKE
to $50k a month using this one weird trick..."

NEGATIVE EXAMPLE 3 — vague promise / passive-income framing (never emulate):
"Hey guys, so I wanted to share something that completely changed my life. I started this side
hustle six months ago and now I'm making passive income while I sleep. The best part? You only
need 2 hours a day and anyone can do it regardless of experience. My students are already making
thousands..."
"""


# ---------------------------------------------------------------------------
# Script generation system prompt
# ---------------------------------------------------------------------------

SCRIPT_SYSTEM_PROMPT = """
You are a senior direct-response copywriter producing a complete video ad
script for ONE approved concept. You work from the structured context
provided in the user message.

SCRIPT FORMAT (mandatory structure):
===================================

PRODUCTION NOTES:
[Brief notes for the videographer: setting, wardrobe, energy level, pacing,
any B-roll suggestions. 3-5 bullet points. These are helper notes, NOT part
of the spoken script.]

---

HOOK 1 (Pattern Interrupt):
[A bold, attention-grabbing opening that stops the scroll in 3 seconds.
Must be a different creative angle from the original concept hook.]

HOOK 2 (Alternative Angle):
[A second distinct opening for the same concept — different emotional
entry point or framing.]

HOOK 3 (Third Option):
[A third distinct opening — test a contrarian, curiosity, or story angle.]

---

BODY:
[The main script. Must follow this structure IN ORDER:]

PAIN:
[Open with the specific pain/problem from the approved concept. Make the
viewer feel seen. Use the avatar's internal monologue and language.]

PROMISE:
[Transition to what's possible. NOT income claims. Frame as relief,
dignity, a real working thing. Use "Earned Calm" as the emotional target.]

PROOF:
[Deploy ONLY proof points provided in the APPROVED_IDEA context. Name
specific credentials, testimonials, and structural proof. NEVER invent
a name, number, statistic, partner, or result not in the provided proof.]

CTA:
[Close with the primary CTA. For cold traffic: "Watch the First Pallet
workshop for $1." Match the funnel stage from the concept's lead_type.
Keep it calm, no urgency theatre, no fake countdowns.]

===================================

ABSOLUTE RULES:
- Script length: 60-180 seconds of A-roll when read aloud (~150-450 words
  for the spoken parts, excluding production notes).
- All three hooks must be DISTINCT — not rewording of the same line.
- ANTI-FABRICATION: Use ONLY facts, names, numbers, testimonials from the
  provided context. If a proof point isn't provided, don't use it.
- COMPLIANCE: No income/earnings claims. No dollar figures tied to what
  members could make. No "passive income." Members are "members" never
  students/customers. Never name a liquidator partner. No hype, no guru
  energy, no lambo imagery, no fake urgency.
- VOICE: Match the client's voice exactly — plainspoken, unhurried,
  operationally specific, anti-hype. Read the VOICE section carefully.
  Marcus sounds like a warehouse manager explaining how something works,
  not a salesman pushing a dream.
- Use curiosity loops and open loops to maintain watch time.
- The body must contain a clear unique mechanism/differentiator explanation.

OUTPUT: Return the complete script as plain text in the exact format above.
Do NOT wrap in markdown code blocks. Do NOT add any preamble or closing
commentary outside the script.
""".strip()


# ---------------------------------------------------------------------------
# Quality review system prompt
# ---------------------------------------------------------------------------

QUALITY_REVIEW_SYSTEM_PROMPT = """
You are a senior quality reviewer for direct-response video ad scripts.
You must evaluate the provided script against EXACTLY 10 checklist items
and a voice/rhythm alignment check.

Evaluate EACH item independently. For each item, return:
- item_number (1-10 or 11 for voice check)
- item_name
- passed (true/false)
- reason (1-2 sentences explaining your judgment)

THE 10-POINT CHECKLIST:
1. Hook opens with a pattern interrupt in the first 3 seconds
2. Clear problem or pain statement present
3. Unique mechanism or differentiator explained
4. Social proof or credibility element included
5. CTA matches funnel stage (cold traffic vs. retargeting)
6. Script length within target range (60 to 180 seconds A-roll)
7. Client brand voice / rhythm alignment (checked against the provided
   voice & talking-style guide)
8. No fabricated claims or unverifiable statistics — cross-check EVERY
   name, number, testimonial, partner count, and credential against the
   PROVIDED PROOF BANK. If ANY claim in the script does not appear in
   the proof bank, this item FAILS.
9. Curiosity or open loop used to maintain watch time
10. VSL structure followed: Pain > Promise > Proof > CTA (in order)

ADDITIONAL CHECK:
11. Voice/rhythm alignment — does the script sound like the client's voice
    as described in the voice guide? Calm, unhurried, plainspoken,
    anti-hype, operationally specific? Or does it drift into guru energy,
    hype, or generic copywriting voice?

PASS RULE: A script passes ONLY if ALL 10 checklist items AND the voice
check pass. A single failure = the script is held.

OUTPUT: Return ONLY valid JSON, no markdown, no backticks:
{
  "passed": true,
  "score": 11,
  "items": [
    {"item_number": 1, "item_name": "...", "passed": true, "reason": "..."},
    ...
  ],
  "overall_notes": "1-2 sentence summary of the script quality"
}
""".strip()


# ---------------------------------------------------------------------------
# Sync DB connection (psycopg2 for Celery tasks)
# ---------------------------------------------------------------------------

def get_sync_connection():
    return psycopg2.connect(
        host=os.getenv("DB_HOST", "localhost"),
        port=int(os.getenv("POSTGRES_PORT", "5432")),
        dbname=os.getenv("POSTGRES_DB", "app_db"),
        user=os.getenv("POSTGRES_USER", "app_user"),
        password=os.getenv("POSTGRES_PASSWORD", ""),
    )


def _dictify(row) -> dict:
    if row is None:
        return None
    result = {}
    for k, v in dict(row).items():
        if isinstance(v, uuid.UUID):
            result[k] = str(v)
        elif isinstance(v, Decimal):
            result[k] = float(v)
        else:
            result[k] = v
    return result


# ---------------------------------------------------------------------------
# Context fetcher (sync — runs inside Celery task)
# ---------------------------------------------------------------------------

def fetch_script_context(conn, client_id_str: str, idea_data: dict) -> dict:
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    cur.execute(
        "SELECT id, name, brand, tone, voice_description, market_stage, core_emotion "
        "FROM clients WHERE id=%s",
        (client_id_str,),
    )
    client = _dictify(cur.fetchone())
    if not client:
        raise ValueError(f"Client {client_id_str} not found")

    cur.execute(
        "SELECT name, description FROM mechanisms WHERE client_id=%s",
        (client_id_str,),
    )
    mechanisms = [_dictify(r) for r in cur.fetchall()]

    cur.execute(
        "SELECT id, name, type, price, description FROM offers WHERE client_id=%s",
        (client_id_str,),
    )
    offers = [_dictify(r) for r in cur.fetchall()]

    cur.execute(
        "SELECT id, type, value, source FROM proof_bank "
        "WHERE client_id=%s AND is_verified=TRUE",
        (client_id_str,),
    )
    proof_bank = [_dictify(r) for r in cur.fetchall()]

    cur.execute(
        "SELECT type, rule FROM constraints WHERE client_id=%s",
        (client_id_str,),
    )
    constraints = [_dictify(r) for r in cur.fetchall()]

    cur.execute(
        "SELECT id, description, age_range, awareness_level, dominant_belief, key_phrase "
        "FROM avatars WHERE client_id=%s",
        (client_id_str,),
    )
    avatar_rows = [_dictify(r) for r in cur.fetchall()]

    pains_by_avatar: dict[str, list] = {}
    if avatar_rows:
        avatar_ids = [av["id"] for av in avatar_rows]
        placeholders = ",".join(["%s"] * len(avatar_ids))
        cur.execute(
            f"SELECT id, avatar_id, pain FROM pain_points WHERE avatar_id IN ({placeholders})",
            avatar_ids,
        )
        for p in cur.fetchall():
            p = _dictify(p)
            pains_by_avatar.setdefault(p["avatar_id"], []).append(
                {"id": p["id"], "pain": p["pain"]}
            )

    audience = []
    for av in avatar_rows:
        entry = dict(av)
        entry["pains"] = pains_by_avatar.get(av["id"], [])
        audience.append(entry)

    cur.execute(
        "SELECT id, name, description FROM angles WHERE client_id=%s",
        (client_id_str,),
    )
    angles = [_dictify(r) for r in cur.fetchall()]

    cur.execute(
        "SELECT id, type, content FROM hooks WHERE client_id=%s",
        (client_id_str,),
    )
    hook_inspiration: dict[str, list] = {}
    for h in cur.fetchall():
        h = _dictify(h)
        hook_inspiration.setdefault(h["type"], []).append(
            {"id": h["id"], "content": h["content"]}
        )

    cur.close()

    return {
        "client": client,
        "mechanisms": mechanisms,
        "offers": offers,
        "proof_bank": proof_bank,
        "constraints": constraints,
        "audience": audience,
        "angles": angles,
        "hook_inspiration": hook_inspiration,
    }


# ---------------------------------------------------------------------------
# Payload builder
# ---------------------------------------------------------------------------

def build_script_payload(context: dict, idea_data: dict) -> str:
    # Resolve avatar description and pain text from context
    avatar_description = ""
    pain_text = ""
    for av in context["audience"]:
        if av["id"] == idea_data.get("target_avatar_id"):
            avatar_description = av.get("description", "")
            for p in av.get("pains", []):
                if p["id"] == idea_data.get("pain_point_id"):
                    pain_text = p["pain"]
                    break
            break

    # Resolve angle name and description
    angle_name = ""
    angle_description = ""
    for a in context["angles"]:
        if a["id"] == idea_data.get("angle_id"):
            angle_name = a.get("name", "")
            angle_description = a.get("description", "")
            break

    # Resolve specific proof points referenced in the idea
    proof_map = {p["id"]: p for p in context["proof_bank"]}
    specific_proof_lines = [
        f"  - [{proof_map[pid]['type']}] {proof_map[pid]['value']}"
        for pid in (idea_data.get("proof_point_ids") or [])
        if pid in proof_map
    ]
    specific_proof_block = (
        "\n".join(specific_proof_lines) if specific_proof_lines else "  (none specified)"
    )

    def j(obj):
        return json.dumps(obj, ensure_ascii=False, indent=2)

    sections = [
        "APPROVED IDEA:",
        f"  Hook: {idea_data.get('hook', '')}",
        f"  Creative Type: {idea_data.get('creative_type', '')}",
        f"  Lead Type: {idea_data.get('lead_type', '')}",
        f"  Angle: {angle_name}",
        f"  Angle Description: {angle_description}",
        f"  Target Avatar: {avatar_description}",
        f"  Pain Addressed: {pain_text}",
        f"  Proof Points Used:\n{specific_proof_block}",
        f"  ICE Reasoning: {idea_data.get('score_reasoning', '')}",
        "",
        "CLIENT IDENTITY:",
        j(context["client"]),
        "",
        "VOICE & TONE:",
        f"  Voice: {context['client'].get('voice_description', '')}",
        f"  Tone: {context['client'].get('tone', '')}",
        "",
        "MECHANISMS:",
        j(context["mechanisms"]),
        "",
        "OFFERS (include prices — $1 trial is critical for CTA):",
        j(context["offers"]),
        "",
        "FULL PROOF BANK (use additional valid proof from here):",
        j(context["proof_bank"]),
        "",
        "HARD RULES:",
        j(context["constraints"]),
        "",
        "AVATARS & PAINS (full set for voice calibration):",
        j(context["audience"]),
        "",
        "HOOK INSPIRATION (do not copy verbatim — inspiration only):",
        j(context["hook_inspiration"]),
        "",
        "NEGATIVE EXAMPLES (never emulate these):",
        NEGATIVE_EXAMPLES,
    ]
    return "\n".join(sections)


# ---------------------------------------------------------------------------
# JSON parser (strips markdown fences if model wraps output)
# ---------------------------------------------------------------------------

def parse_json_safely(text: str) -> dict:
    text = text.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        text = "\n".join(lines[1:])  # drop opening fence line
        if text.rstrip().endswith("```"):
            text = "\n".join(text.rstrip().split("\n")[:-1])
    return json.loads(text.strip())


# ---------------------------------------------------------------------------
# DB write helpers
# ---------------------------------------------------------------------------

def save_script(conn, idea_id: str, client_id: str, content: str, status: str = "pending_review") -> str:
    script_id = str(uuid.uuid4())
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO scripts (id, idea_id, client_id, content, status) "
        "VALUES (%s, %s, %s, %s, %s)",
        (script_id, str(idea_id), str(client_id), content, status),
    )
    cur.close()
    return script_id


def update_script_status(conn, script_id: str, status: str):
    cur = conn.cursor()
    cur.execute("UPDATE scripts SET status=%s WHERE id=%s", (status, str(script_id)))
    cur.close()


def save_quality_review(conn, script_id: str, passed: bool, score: int, full_review: dict):
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO quality_reviews (id, script_id, passed, score, feedback) "
        "VALUES (%s, %s, %s, %s, %s)",
        (
            str(uuid.uuid4()),
            str(script_id),
            passed,
            score,
            psycopg2.extras.Json(full_review),
        ),
    )
    cur.close()


# ---------------------------------------------------------------------------
# Quality review runner
# ---------------------------------------------------------------------------

def run_quality_review(conn, script_id: str, script_content: str, context: dict, idea_data: dict) -> dict:
    avatar_description = ""
    for av in context["audience"]:
        if av["id"] == idea_data.get("target_avatar_id"):
            avatar_description = av.get("description", "")
            break

    payload = "\n".join([
        "SCRIPT TO REVIEW:",
        script_content,
        "",
        "APPROVED IDEA IT WAS BASED ON:",
        f"  Hook: {idea_data.get('hook', '')}",
        f"  Lead Type: {idea_data.get('lead_type', '')}",
        f"  Target Avatar: {avatar_description}",
        "",
        "CLIENT VOICE GUIDE:",
        f"  {context['client'].get('voice_description', '')}",
        f"  {context['client'].get('tone', '')}",
        "",
        "FULL PROOF BANK (for fabrication check):",
        json.dumps(context["proof_bank"], ensure_ascii=False, indent=2),
        "",
        "HARD RULES:",
        json.dumps(context["constraints"], ensure_ascii=False, indent=2),
    ])

    service = _get_gemini_service()
    result_text = service.generate_text(payload, QUALITY_REVIEW_SYSTEM_PROMPT, temperature=0)

    review = parse_json_safely(result_text)

    save_quality_review(conn, script_id, review["passed"], review["score"], review)

    return review
