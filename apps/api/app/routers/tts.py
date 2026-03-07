"""Text-to-speech endpoints."""
from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from ..providers.tts.factory import get_tts_client
from ..providers.tts.base import TTSRequest

router = APIRouter(tags=["tts"])


class SynthesizeRequest(BaseModel):
    text: str
    voice: str | None = None
    provider: str | None = None  # vibevoice|elevenlabs|openai
    speed: float = 1.0


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
        raise HTTPException(500, f"TTS synthesis failed: {e}")

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
