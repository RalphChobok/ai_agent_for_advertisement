import os

from dotenv import load_dotenv
from openai import OpenAI

load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))

_client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

EMBEDDING_MODEL = "text-embedding-3-small"


def get_embedding(text: str) -> list[float]:
    response = _client.embeddings.create(input=text, model=EMBEDDING_MODEL)
    return response.data[0].embedding


def get_embeddings_batch(texts: list[str]) -> list[list[float]]:
    """Embed a batch of texts in one API call. Max ~8000 tokens per batch."""
    if not texts:
        return []
    response = _client.embeddings.create(input=texts, model=EMBEDDING_MODEL)
    return [item.embedding for item in sorted(response.data, key=lambda x: x.index)]


def idea_to_embed_text(idea: dict) -> str:
    """Combine semantically meaningful idea fields into a single string for embedding."""
    parts = [
        f"Hook: {idea.get('hook', '')}",
        f"Angle: {idea.get('angle_name', idea.get('angle_id', ''))}",
        f"Creative type: {idea.get('creative_type', '')}",
        f"Lead type: {idea.get('lead_type', '')}",
        f"Avatar: {idea.get('avatar_description', idea.get('target_avatar_id', ''))}",
        f"Pain: {idea.get('pain', idea.get('pain_point_id', ''))}",
    ]
    return " | ".join(parts)
