"""Bhashini ULCA pipeline client (BHASHINI_MODE=real): ASR, translation and TTS.

Two-step protocol: `getModelsPipeline` (authenticated with ULCA user id + API key) returns
the inference endpoint, its auth header and a serviceId per task; the compute call then
runs the task. Pipeline configs are cached for an hour. Needs approved Bhashini keys."""

import base64
import time
from typing import Any

import httpx

from app.config import get_settings

CONFIG_URL = "https://meity-auth.ulcacontrib.org/ulca/apis/v0/model/getModelsPipeline"
_config_cache: dict[tuple[str, str, str], tuple[float, dict[str, Any]]] = {}


class BhashiniNotConfigured(RuntimeError):
    pass


def configured() -> bool:
    s = get_settings()
    return s.bhashini_mode == "real" and bool(s.bhashini_user_id and s.bhashini_api_key)


async def _pipeline(task: str, source: str, target: str = "") -> dict[str, Any]:
    if not configured():
        raise BhashiniNotConfigured("BHASHINI_MODE=real needs BHASHINI_USER_ID and BHASHINI_API_KEY")
    cache_key = (task, source, target)
    hit = _config_cache.get(cache_key)
    if hit and time.monotonic() - hit[0] < 3600:
        return hit[1]
    s = get_settings()
    language: dict[str, str] = {"sourceLanguage": source}
    if target:
        language["targetLanguage"] = target
    body = {"pipelineTasks": [{"taskType": task, "config": {"language": language}}],
            "pipelineRequestConfig": {"pipelineId": s.bhashini_pipeline_id}}
    async with httpx.AsyncClient(timeout=4.0) as client:
        resp = await client.post(CONFIG_URL, json=body, headers={"userID": s.bhashini_user_id or "", "ulcaApiKey": s.bhashini_api_key or ""})
        resp.raise_for_status()
        data = resp.json()
    endpoint = data["pipelineInferenceAPIEndPoint"]
    service_id = data["pipelineResponseConfig"][0]["config"][0]["serviceId"]
    config = {"url": endpoint["callbackUrl"], "auth": {endpoint["inferenceApiKey"]["name"]: endpoint["inferenceApiKey"]["value"]},
              "service_id": service_id}
    _config_cache[cache_key] = (time.monotonic(), config)
    return config


async def _compute(config: dict[str, Any], task: dict[str, Any], input_data: dict[str, Any]) -> dict[str, Any]:
    async with httpx.AsyncClient(timeout=4.0) as client:
        resp = await client.post(config["url"], json={"pipelineTasks": [task], "inputData": input_data}, headers=config["auth"])
        resp.raise_for_status()
        return resp.json()  # type: ignore[no-any-return]


async def asr(audio_wav_or_ogg: bytes, lang: str, audio_format: str) -> str:
    config = await _pipeline("asr", lang)
    task = {"taskType": "asr", "config": {"language": {"sourceLanguage": lang}, "serviceId": config["service_id"],
                                          "audioFormat": audio_format, "samplingRate": 16000}}
    data = await _compute(config, task, {"audio": [{"audioContent": base64.b64encode(audio_wav_or_ogg).decode()}]})
    return str(data["pipelineResponse"][0]["output"][0]["source"]).strip()


async def translate(text: str, source: str, target: str) -> str:
    config = await _pipeline("translation", source, target)
    task = {"taskType": "translation", "config": {"language": {"sourceLanguage": source, "targetLanguage": target},
                                                  "serviceId": config["service_id"]}}
    data = await _compute(config, task, {"input": [{"source": text}]})
    return str(data["pipelineResponse"][0]["output"][0]["target"]).strip()


async def tts(text: str, lang: str, gender: str = "female") -> bytes:
    config = await _pipeline("tts", lang)
    task = {"taskType": "tts", "config": {"language": {"sourceLanguage": lang}, "serviceId": config["service_id"],
                                          "gender": gender, "samplingRate": 16000}}
    data = await _compute(config, task, {"input": [{"source": text}]})
    return base64.b64decode(data["pipelineResponse"][0]["audio"][0]["audioContent"])
