import asyncio
import base64
import io
import os
import re
import uuid
import wave
from pathlib import Path

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import FileResponse, StreamingResponse

router = APIRouter()

TTS_VOICE = "Enceladus"
TTS_MODEL = "gemini-2.5-flash-preview-tts"
DIRECTOR_MODEL = "gemini-2.5-flash"
CHUNK_MAX_CHARS = 800
DEFAULT_AUDIO_DIR = Path(__file__).resolve().parent.parent / "generated_audio"

_DIRECTOR_PROMPT = """You are an expert direct-response audio director. Take this specific ad copy text and rewrite it into an optimized Speech Synthesis format.
Keep every single word identical, but insert explicit timing flags using `<break time="XXXms"/>` tags.

Follow these pacing directions for the character ({voice_hint}):
- Insert an explicit 1000ms emotional break after heavy sentences involving doubt, losing money, fear, or frustration.
- Insert a 600ms pacing break between major thematic paragraph transitions (problem to promise, promise to proof).
- Insert natural 300ms breathing room around key emphasis transitions.
- Return ONLY the clean, marked-up text inside a single <speak> block. Do not include any explanation or commentary outside the <speak> block.

Script to process:
{script_text}"""


# ---------------------------------------------------------------------------
# Script parser
# ---------------------------------------------------------------------------

def _parse_script(content: str) -> dict:
    """
    Returns {"hooks": {1: str, 2: str, 3: str}, "body": str}.
    Strips PRODUCTION NOTES entirely; strips BODY/PAIN/PROMISE/PROOF/CTA labels
    from the body section but keeps their paragraph content.
    """
    sections = re.split(r'\n\s*---\s*\n', content)
    # sections[0] = production notes, [1] = hooks, [2] = body
    hooks_section = sections[1] if len(sections) > 1 else content
    body_raw = sections[2] if len(sections) > 2 else ""

    hooks: dict[int, str] = {}
    for n in (1, 2, 3):
        pat = rf'HOOK\s+{n}\s*\([^)]*\)\s*:\s*\n(.*?)(?=\nHOOK\s+\d|\Z)'
        m = re.search(pat, hooks_section, re.DOTALL | re.IGNORECASE)
        hooks[n] = m.group(1).strip() if m else ""

    label_pat = re.compile(r'^\s*(BODY|PAIN|PROMISE|PROOF|CTA)\s*:\s*$', re.IGNORECASE | re.MULTILINE)
    body_clean = label_pat.sub('', body_raw).strip()
    body_clean = re.sub(r'\n{3,}', '\n\n', body_clean)

    return {"hooks": hooks, "body": body_clean}


# ---------------------------------------------------------------------------
# Chunker (sentence-aware)
# ---------------------------------------------------------------------------

def _split_into_chunks(text: str, max_chars: int = CHUNK_MAX_CHARS) -> list[str]:
    sentence_pat = re.compile(r'(?<=[.!?])\s+')
    sentences = sentence_pat.split(text.strip())
    chunks: list[str] = []
    current = ""
    for sent in sentences:
        sent = sent.strip()
        if not sent:
            continue
        candidate = (current + " " + sent).strip() if current else sent
        if len(candidate) <= max_chars:
            current = candidate
        else:
            if current:
                chunks.append(current.strip())
            current = sent
    if current:
        chunks.append(current.strip())
    return chunks or [text]


# ---------------------------------------------------------------------------
# Blocking helpers (run inside asyncio.to_thread)
# ---------------------------------------------------------------------------

def _director_pass(client, script_text: str, voice_hint: str) -> str:
    """Add SSML pacing tags via Gemini text model."""
    from google.genai import types

    prompt = _DIRECTOR_PROMPT.format(voice_hint=voice_hint, script_text=script_text)
    response = client.models.generate_content(
        model=DIRECTOR_MODEL,
        contents=prompt,
        config=types.GenerateContentConfig(temperature=0),
    )
    result = response.text
    result = result.replace("```xml", "").replace("```html", "").replace("```", "").strip()
    result = re.sub(r'^\s*<speak>\s*', '', result)
    result = re.sub(r'\s*</speak>\s*$', '', result).strip()
    return result


def _synthesize_chunk(client, chunk_text: str) -> bytes:
    """Send one SSML chunk to Gemini TTS; return raw PCM bytes."""
    from google.genai import types

    response = client.models.generate_content(
        model=TTS_MODEL,
        contents=f"<speak>{chunk_text}</speak>",
        config=types.GenerateContentConfig(
            response_modalities=["AUDIO"],
            speech_config=types.SpeechConfig(
                voice_config=types.VoiceConfig(
                    prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name=TTS_VOICE),
                )
            ),
        ),
    )
    part = response.candidates[0].content.parts[0]
    if hasattr(part, "inline_data") and part.inline_data:
        raw = part.inline_data.data
        return raw if isinstance(raw, bytes) else base64.b64decode(raw)
    raise ValueError("TTS: no audio bytes in response")


def _pcm_to_wav(pcm_bytes: bytes, sample_rate: int = 24000) -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)       # 16-bit PCM
        wf.setframerate(sample_rate)
        wf.writeframes(pcm_bytes)
    return buf.getvalue()


def _audio_dir() -> Path:
    directory = Path(os.getenv("AUDIO_OUTPUT_DIR", DEFAULT_AUDIO_DIR))
    directory.mkdir(parents=True, exist_ok=True)
    return directory


def _audio_filename(script_id: uuid.UUID, hook_number: int) -> str:
    return f"script_{script_id}_hook{hook_number}.wav"


def _audio_path(script_id: uuid.UUID, hook_number: int) -> Path:
    return _audio_dir() / _audio_filename(script_id, hook_number)


def _audio_entry(script_id: uuid.UUID, hook_number: int, path: Path) -> dict:
    filename = path.name
    return {
        "id": f"{script_id}-hook-{hook_number}",
        "hook_index": hook_number,
        "label": f"Hook {hook_number} + Body",
        "file_path": str(path),
        "url": f"/api/audio/{filename}",
    }


# ---------------------------------------------------------------------------
# Endpoint
# ---------------------------------------------------------------------------

@router.get("/scripts/{script_id}/audio")
async def list_script_audio(
    script_id: uuid.UUID,
    request: Request,
):
    pool = request.app.state.pool
    async with pool.acquire() as conn:
        exists = await conn.fetchval("SELECT EXISTS(SELECT 1 FROM scripts WHERE id = $1)", script_id)

    if not exists:
        raise HTTPException(status_code=404, detail="Script not found")

    entries = []
    for hook_number in (1, 2, 3):
        path = _audio_path(script_id, hook_number)
        if path.exists():
            entries.append(_audio_entry(script_id, hook_number, path))
    return entries


@router.get("/audio/{filename}")
async def serve_audio_file(filename: str):
    if "/" in filename or "\\" in filename or not filename.endswith(".wav"):
        raise HTTPException(status_code=400, detail="Invalid audio filename")

    path = _audio_dir() / filename
    if not path.exists() or not path.is_file():
        raise HTTPException(status_code=404, detail="Audio file not found")

    return FileResponse(path, media_type="audio/wav", filename=filename)


@router.post("/scripts/{script_id}/audio")
async def generate_script_audio(
    script_id: uuid.UUID,
    request: Request,
    hook_number: int = Query(default=1, ge=1, le=3, description="Which hook variant to synthesize (1, 2, or 3)"),
):
    """
    Generate a WAV voiceover for one hook variant of a script.
    The audio is: Hook N text + body (PAIN + PROMISE + PROOF + CTA content).
    Production Notes and section labels are stripped; pacing tags are added
    via a Gemini director pass before synthesis.
    """
    pool = request.app.state.pool
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT s.content, c.voice_description, c.brand
            FROM scripts s
            JOIN clients c ON s.client_id = c.id
            WHERE s.id = $1
            """,
            script_id,
        )
    if not row:
        raise HTTPException(status_code=404, detail="Script not found")

    output_path = _audio_path(script_id, hook_number)
    if output_path.exists():
        return FileResponse(output_path, media_type="audio/wav", filename=output_path.name)

    content = row["content"] or ""
    voice_hint = f"{row['brand']} — {row['voice_description'] or 'calm, unhurried, conversational, direct'}"

    parsed = _parse_script(content)
    hook_text = parsed["hooks"].get(hook_number, "")
    if not hook_text:
        raise HTTPException(status_code=422, detail=f"Hook {hook_number} not found in script")

    ad_text = f"{hook_text}\n\n{parsed['body']}"

    def _generate() -> bytes:
        from google import genai as google_genai

        api_key = os.getenv("GEMINI_API_KEY")
        if not api_key:
            raise ValueError("GEMINI_API_KEY not set")

        g_client = google_genai.Client(api_key=api_key)

        print(f"[TTS] Hook {hook_number}: running director pass...")
        marked_inner = _director_pass(g_client, ad_text, voice_hint)
        chunks = _split_into_chunks(marked_inner)
        print(f"[TTS] Hook {hook_number}: {len(chunks)} chunk(s) to synthesize")

        all_pcm: list[bytes] = []
        for i, chunk in enumerate(chunks):
            print(f"[TTS] Hook {hook_number} chunk {i + 1}/{len(chunks)}: {len(chunk)} chars")
            all_pcm.append(_synthesize_chunk(g_client, chunk))

        return _pcm_to_wav(b"".join(all_pcm))

    try:
        wav_bytes = await asyncio.to_thread(_generate)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Audio generation failed: {exc}")

    output_path.write_bytes(wav_bytes)

    return StreamingResponse(
        io.BytesIO(wav_bytes),
        media_type="audio/wav",
        headers={
            "Content-Disposition": f'attachment; filename="hook{hook_number}_{script_id}.wav"',
            "Content-Length": str(len(wav_bytes)),
        },
    )
