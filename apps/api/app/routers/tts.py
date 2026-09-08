"""Text-to-speech endpoints."""
from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from ..providers.tts.factory import get_tts_client
from ..providers.tts.base import TTSRequest
from ..discussion.engine import AGENT_VOICES

router = APIRouter(tags=["tts"])

MAX_TTS_TEXT_LENGTH = 5000


class SynthesizeRequest(BaseModel):
    text: str = Field(..., max_length=MAX_TTS_TEXT_LENGTH)
    voice: str | None = None
    provider: str | None = None  # vibevoice|elevenlabs|openai
    speed: float = Field(1.0, ge=0.25, le=4.0)


@router.post("/tts/synthesize")
async def synthesize_speech(req: SynthesizeRequest):
    """
    Synthesize speech from text.

    Returns MP3 audio data.
    """
    try:
        client = get_tts_client(req.provider)
    except ValueError as e:
        raise HTTPException(400, str(e))

    try:
        audio_data = await client.synthesize(
            TTSRequest(
                text=req.text,
                voice=req.voice,
                speed=req.speed,
            )
        )
    except Exception as e:
        print(f"TTS synthesis error: {e}")
        raise HTTPException(500, "TTS synthesis failed")

    return StreamingResponse(
        iter([audio_data]),
        media_type="audio/mpeg",
        headers={
            "Content-Disposition": "attachment; filename=speech.mp3",
        },
    )


@router.post("/tts/stream")
async def stream_speech(req: SynthesizeRequest):
    """
    Stream synthesized speech.

    Returns chunked MP3 audio data for faster time-to-first-audio.
    """
    try:
        client = get_tts_client(req.provider)
    except ValueError as e:
        raise HTTPException(400, str(e))

    async def generate():
        try:
            async for chunk in client.stream(
                TTSRequest(
                    text=req.text,
                    voice=req.voice,
                    speed=req.speed,
                )
            ):
                yield chunk
        except Exception as e:
            # Log error but can't easily propagate in streaming response
            print(f"TTS streaming error: {e}")

    return StreamingResponse(
        generate(),
        media_type="audio/mpeg",
        headers={
            "Transfer-Encoding": "chunked",
        },
    )


@router.get("/tts/voices")
def list_voices(provider: str | None = Query(None)):
    """List available voices for a provider."""
    voices = {
        "openai": ["alloy", "echo", "fable", "onyx", "nova", "shimmer"],
        "elevenlabs": [
            {"id": "21m00Tcm4TlvDq8ikWAM", "name": "Rachel"},
            {"id": "EXAVITQu4vr4xnSDxMaL", "name": "Sarah"},
            {"id": "D38z5RcWu1voky8WS1ja", "name": "Fin"},
            {"id": "TX3LPaxmHKxFdv7VOQHJ", "name": "Liam"},
        ],
        "vibevoice": ["alloy", "echo", "fable", "onyx", "nova", "shimmer"],
    }

    if provider:
        return {"provider": provider, "voices": voices.get(provider, [])}

    return {"voices": voices}


@router.get("/tts/agent-voices")
def get_agent_voices():
    """Return the per-agent voice mapping used in discussion streaming.

    The frontend can use this to pre-configure TTS voices for each agent.
    The same mapping is also sent in ``message_start`` and ``sentence_ready``
    SSE events during discussion streaming.
    """
    return {
        "agent_voices": AGENT_VOICES,
        "agents": {
            role: {"voice": voice, "display_name": name}
            for role, voice, name in [
                ("facilitator", AGENT_VOICES["facilitator"], "Sam"),
                ("close_reader", AGENT_VOICES["close_reader"], "Ellis"),
                ("skeptic", AGENT_VOICES["skeptic"], "Kit"),
            ]
        },
    }
