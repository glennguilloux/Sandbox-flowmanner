"""
Multimedia Generation Tools — Stable Diffusion Pipeline.

stable_diffusion_pipeline → Generate images via Stable Diffusion with multi-provider
    routing (Replicate, HuggingFace, local), txt2img, img2img, inpainting,
    ControlNet, LoRA, batch generation, and upscaling support.
"""

from __future__ import annotations

import base64
import hashlib
import json
import logging
import os
import time
from typing import Any, Literal

import httpx
from pydantic import BaseModel, Field, field_validator, model_validator

from app.tools.base import BaseTool, ToolInput, ToolMetadata, ToolResult, register_tool

logger = logging.getLogger(__name__)

# Environment config
SD_STORAGE_DIR = os.getenv("SD_STORAGE_DIR", "/tmp/flowmanner/sd_images")
SD_TIMEOUT = int(os.getenv("SD_TIMEOUT", "300"))

# API keys per provider
REPLICATE_API_TOKEN = os.getenv("REPLICATE_API_TOKEN", "")
HF_API_TOKEN = os.getenv("HF_API_TOKEN", "")
LOCAL_SD_ENDPOINT = os.getenv("LOCAL_SD_ENDPOINT", "http://localhost:7860")

MODES = ("txt2img", "img2img", "inpaint")
PROVIDERS = ("replicate", "huggingface", "local")

# Well-known Replicate model versions (use 'latest' as default when unknown)
REPLICATE_MODELS = {
    "stabilityai/stable-diffusion-xl-base-1.0": "stability-ai/sdxl:39ed52f2a78e934b3ba6e2a89f5b1c712de7dfea535525255b1aa35c5565e08b",
}

SCHEDULERS = (
    "DDIM",
    "DPMSolverMultistep",
    "EulerAncestralDiscrete",
    "EulerDiscrete",
    "PNDM",
    "LMSDiscrete",
    "DPM2",
    "DPM2Ancestral",
)

SDXL_DEFAULT_SIZE = 1024
SDXL_DEFAULT_STEPS = 30


class ControlNetUnit(BaseModel):
    """ControlNet configuration for guided image generation."""

    control_type: Literal[
        "canny", "depth", "pose", "scribble", "seg", "normal", "lineart"
    ] = Field(
        "canny",
        description="ControlNet preprocessing type",
    )
    image_url: str = Field(
        ...,
        description="URL or base64 data URI of the control image",
    )
    weight: float = Field(
        0.8, ge=0.0, le=2.0, description="ControlNet conditioning scale"
    )
    start_percent: float = Field(
        0.0, ge=0.0, le=1.0, description="When ControlNet starts (0-1)"
    )
    end_percent: float = Field(
        1.0, ge=0.0, le=1.0, description="When ControlNet ends (0-1)"
    )


class LoRAUnit(BaseModel):
    """LoRA model configuration."""

    lora_url: str = Field(
        ...,
        description="URL or HuggingFace repo ID of the LoRA weights",
    )
    scale: float = Field(0.75, ge=0.0, le=2.0, description="LoRA strength multiplier")
    trigger_word: str | None = Field(None, description="Trigger word for the LoRA")


class StableDiffusionPipelineInput(ToolInput):
    """Input schema: prompt, mode, model, provider, width/height, steps, controlnet, loras, etc."""

    prompt: str = Field(
        ...,
        min_length=1,
        max_length=5000,
        description="Image generation prompt",
    )
    negative_prompt: str = Field(
        "",
        description="Elements to exclude from the generated image",
    )
    mode: Literal["txt2img", "img2img", "inpaint"] = Field(
        "txt2img",
        description="Generation mode",
    )
    model: str = Field(
        "stabilityai/stable-diffusion-xl-base-1.0",
        description="Model identifier (HuggingFace repo or Replicate model)",
    )
    provider: Literal["replicate", "huggingface", "local"] = Field(
        "replicate",
        description="Inference provider",
    )
    width: int = Field(
        SDXL_DEFAULT_SIZE,
        ge=256,
        le=2048,
        description="Image width in pixels (must be multiple of 8)",
    )
    height: int = Field(
        SDXL_DEFAULT_SIZE,
        ge=256,
        le=2048,
        description="Image height in pixels (must be multiple of 8)",
    )
    num_inference_steps: int = Field(
        SDXL_DEFAULT_STEPS,
        ge=1,
        le=150,
        description="Number of denoising steps",
    )
    guidance_scale: float = Field(
        7.5,
        ge=1.0,
        le=20.0,
        description="Classifier-free guidance scale",
    )
    seed: int | None = Field(
        None,
        description="Random seed for reproducible generation",
    )
    num_images: int = Field(
        1,
        ge=1,
        le=4,
        description="Number of images to generate in batch",
    )
    scheduler: Literal[
        "DDIM",
        "DPMSolverMultistep",
        "EulerAncestralDiscrete",
        "EulerDiscrete",
        "PNDM",
        "LMSDiscrete",
        "DPM2",
        "DPM2Ancestral",
    ] = Field(
        "DPMSolverMultistep",
        description="Scheduler for the diffusion process",
    )
    init_image_url: str | None = Field(
        None,
        description="Initial image URL/base64 for img2img and inpainting modes",
    )
    mask_image_url: str | None = Field(
        None,
        description="Mask image URL/base64 for inpainting mode",
    )
    denoising_strength: float = Field(
        0.75,
        ge=0.0,
        le=1.0,
        description="Denoising strength for img2img (0=keep original, 1=full regeneration)",
    )
    controlnet_units: list[ControlNetUnit] | None = Field(
        None,
        description="ControlNet conditioning units",
    )
    loras: list[LoRAUnit] | None = Field(
        None,
        description="LoRA models to apply",
    )
    use_refiner: bool = Field(
        False,
        description="Apply SDXL refiner pass for higher quality",
    )
    refiner_start: float = Field(
        0.8,
        ge=0.0,
        le=1.0,
        description="Fraction of steps at which to start the refiner (0.8 = 80% through denoising)",
    )
    upscale_factor: float | None = Field(
        None,
        ge=1.0,
        le=4.0,
        description="Upscale output by this factor using ESRGAN",
    )
    mask_blur: int = Field(
        4,
        ge=0,
        le=64,
        description="Gaussian blur radius for the inpainting mask",
    )
    mask_invert: bool = Field(
        False,
        description="Invert the mask (white becomes black and vice versa)",
    )
    clip_skip: int = Field(
        1,
        ge=1,
        le=12,
        description="Number of CLIP layers to skip (higher = less prompt adherence, more creative)",
    )
    api_key: str | None = Field(
        None,
        description="API key for the selected provider. Uses env var if omitted.",
    )
    save_to_storage: bool = Field(
        True,
        description="Download and save generated images to local storage",
    )

    @field_validator("init_image_url", "mask_image_url")
    @classmethod
    def validate_image_urls(cls, v: str | None) -> str | None:
        """Validate image URLs are safe (http/https only, block internal IPs)."""
        if v is None:
            return v
        # Allow base64 data URIs
        if v.startswith("data:"):
            return v
        # Require http/https scheme
        if not v.startswith(("http://", "https://")):
            raise ValueError(
                f"Image URL must use http/https scheme or data URI, got: {v[:80]}"
            )
        # Block internal IPs (SSRF protection)
        from urllib.parse import urlparse

        parsed = urlparse(v)
        hostname = parsed.hostname or ""
        blocked_hosts = {"localhost", "127.0.0.1", "0.0.0.0", "::1"}
        blocked_prefixes = (
            "10.",
            "172.16.",
            "172.17.",
            "172.18.",
            "172.19.",
            "172.20.",
            "172.21.",
            "172.22.",
            "172.23.",
            "172.24.",
            "172.25.",
            "172.26.",
            "172.27.",
            "172.28.",
            "172.29.",
            "172.30.",
            "172.31.",
            "192.168.",
            "169.254.",
        )
        if hostname in blocked_hosts or hostname.startswith(blocked_prefixes):
            raise ValueError(f"Image URL hostname not allowed: {hostname}")
        return v

    @model_validator(mode="after")
    def validate_dimensions(self):
        if self.width % 8 != 0 or self.height % 8 != 0:
            raise ValueError("Width and height must be multiples of 8")
        return self

    @model_validator(mode="after")
    def validate_mode_inputs(self):
        if self.mode in ("img2img", "inpaint") and not self.init_image_url:
            raise ValueError(f"init_image_url is required for {self.mode} mode")
        if self.mode == "inpaint" and not self.mask_image_url:
            raise ValueError("mask_image_url is required for inpainting mode")
        return self


class StableDiffusionPipelineTool(BaseTool):
    """Generate images via Stable Diffusion with multi-provider routing."""

    def __init__(self):
        metadata = ToolMetadata(
            tool_id="stable_diffusion_pipeline",
            name="Stable Diffusion Pipeline",
            description=(
                "Generate images via Stable Diffusion with multi-provider routing "
                "(Replicate, HuggingFace, local). Supports txt2img, img2img, "
                "inpainting, ControlNet, LoRA, batch generation, and upscaling."
            ),
            category="multimedia-generation",
            input_schema=StableDiffusionPipelineInput.schema_extra(),
            output_schema={
                "type": "object",
                "properties": {
                    "images": {"type": "array", "items": {"type": "object"}},
                    "model": {"type": "string"},
                    "provider": {"type": "string"},
                    "mode": {"type": "string"},
                    "num_inference_steps": {"type": "integer"},
                    "seed": {"type": "integer"},
                    "cost_usd": {"type": "number"},
                    "generation_time_ms": {"type": "integer"},
                    "success": {"type": "boolean"},
                },
            },
            tags=["image", "stable-diffusion", "generation", "multimedia", "replicate"],
            requires_auth=True,
            timeout_seconds=SD_TIMEOUT + 30,
        )
        super().__init__(metadata=metadata)

    async def execute(self, input_data: dict) -> ToolResult:
        try:
            validated = StableDiffusionPipelineInput(**input_data)
        except Exception as e:
            return ToolResult.error_result(
                tool_id=self.tool_id, error=f"Invalid input: {e}"
            )

        start = time.monotonic()

        try:
            if validated.provider == "replicate":
                result = await self._run_replicate(validated, start)
            elif validated.provider == "huggingface":
                result = await self._run_huggingface(validated, start)
            elif validated.provider == "local":
                result = await self._run_local(validated, start)
            else:
                return ToolResult.error_result(
                    tool_id=self.tool_id,
                    error=f"Unknown provider: {validated.provider}",
                )

            return result

        except httpx.HTTPStatusError as e:
            detail = ""
            try:
                detail = str(e.response.json())
            except Exception:
                detail = e.response.text[:500]
            return ToolResult.error_result(
                tool_id=self.tool_id, error=f"Provider API error: {detail}"
            )
        except Exception as e:
            logger.exception("stable_diffusion_pipeline failed")
            return ToolResult.error_result(tool_id=self.tool_id, error=str(e))

    async def _run_replicate(
        self, validated: StableDiffusionPipelineInput, start: float
    ) -> ToolResult:
        """Run inference via Replicate API."""
        if not REPLICATE_API_TOKEN and not validated.api_key:
            return ToolResult.error_result(
                tool_id=self.tool_id, error="Replicate API token required"
            )

        # Resolve model version
        model_version = REPLICATE_MODELS.get(
            validated.model,
            f"stability-ai/sdxl:39ed52f2a78e934b3ba6e2a89f5b1c712de7dfea535525255b1aa35c5565e08b",
        )

        headers = {
            "Authorization": f"Token {validated.api_key or REPLICATE_API_TOKEN}",
            "Content-Type": "application/json",
        }

        # Build Replicate input
        replicate_input: dict[str, Any] = {
            "prompt": validated.prompt,
            "negative_prompt": validated.negative_prompt or "",
            "width": validated.width,
            "height": validated.height,
            "num_inference_steps": validated.num_inference_steps,
            "guidance_scale": validated.guidance_scale,
            "num_outputs": validated.num_images,
            "scheduler": validated.scheduler,
        }

        if validated.seed is not None:
            replicate_input["seed"] = validated.seed

        if validated.mode == "img2img" and validated.init_image_url:
            replicate_input["image"] = validated.init_image_url
            replicate_input["prompt_strength"] = validated.denoising_strength

        if validated.mode == "inpaint" and validated.init_image_url:
            replicate_input["image"] = validated.init_image_url
            replicate_input["mask"] = validated.mask_image_url
            replicate_input["mask_blur"] = validated.mask_blur
            replicate_input["mask_invert"] = validated.mask_invert

        if validated.use_refiner:
            replicate_input["refine"] = "expert_ensemble_refiner"
            replicate_input["refine_steps"] = int(
                (1.0 - validated.refiner_start) * validated.num_inference_steps
            )

        if validated.clip_skip > 1:
            replicate_input["clip_skip"] = validated.clip_skip

        if validated.loras:
            replicate_input["lora_weights"] = ",".join(
                f"{l.lora_url}:{l.scale}" for l in validated.loras
            )

        async with httpx.AsyncClient(timeout=SD_TIMEOUT) as client:
            # Create prediction
            create_resp = await client.post(
                "https://api.replicate.com/v1/predictions",
                headers=headers,
                json={"version": model_version, "input": replicate_input},
            )
            create_resp.raise_for_status()
            prediction = create_resp.json()

            # Poll for completion
            poll_url = prediction.get("urls", {}).get("get", "")
            deadline = time.monotonic() + SD_TIMEOUT
            while time.monotonic() < deadline:
                await asyncio.sleep(3)
                status_resp = await client.get(poll_url, headers=headers)
                status_resp.raise_for_status()
                status_data = status_resp.json()

                if status_data.get("status") == "succeeded":
                    output_urls = status_data.get("output", [])
                    images = await self._process_output_images(
                        output_urls,
                        validated,
                        start,
                    )
                    gen_time = int((time.monotonic() - start) * 1000)
                    return ToolResult.success_result(
                        tool_id=self.tool_id,
                        result={
                            "images": images,
                            "model": validated.model,
                            "provider": "replicate",
                            "mode": validated.mode,
                            "num_inference_steps": validated.num_inference_steps,
                            "seed": validated.seed,
                            "cost_usd": 0.05 * validated.num_images,  # approximate
                            "generation_time_ms": gen_time,
                            "success": True,
                        },
                    )

                elif status_data.get("status") == "failed":
                    return ToolResult.error_result(
                        tool_id=self.tool_id,
                        error=f"Replicate prediction failed: {status_data.get('error', 'unknown')}",
                    )

            return ToolResult.error_result(
                tool_id=self.tool_id, error="Replicate generation timed out"
            )

    async def _run_huggingface(
        self, validated: StableDiffusionPipelineInput, start: float
    ) -> ToolResult:
        """Run inference via HuggingFace Inference API."""
        token = validated.api_key or HF_API_TOKEN
        if not token:
            return ToolResult.error_result(
                tool_id=self.tool_id, error="HuggingFace API token required"
            )

        headers = {"Authorization": f"Bearer {token}"}
        url = f"https://api-inference.huggingface.co/models/{validated.model}"

        body = {
            "inputs": validated.prompt,
            "parameters": {
                "negative_prompt": validated.negative_prompt or "",
                "width": validated.width,
                "height": validated.height,
                "num_inference_steps": validated.num_inference_steps,
                "guidance_scale": validated.guidance_scale,
                "num_images_per_prompt": validated.num_images,
            },
        }

        if validated.seed is not None:
            body["parameters"]["seed"] = validated.seed

        async with httpx.AsyncClient(timeout=SD_TIMEOUT) as client:
            resp = await client.post(url, headers=headers, json=body)
            resp.raise_for_status()

            content_type = resp.headers.get("content-type", "")
            if "image" in content_type:
                # Single image returned as bytes
                images = [{"index": 0, "data": base64.b64encode(resp.content).decode()}]
                if validated.save_to_storage:
                    path = self._save_image(resp.content, validated.model, 0)
                    images[0]["local_path"] = path
            else:
                # JSON response with URLs
                data = resp.json()
                if isinstance(data, list):
                    output_urls = [
                        d.get("url", d) if isinstance(d, dict) else d for d in data
                    ]
                else:
                    output_urls = [
                        data.get("url", data) if isinstance(data, dict) else data
                    ]

                images = await self._process_output_images(
                    output_urls, validated, start
                )

            gen_time = int((time.monotonic() - start) * 1000)
            return ToolResult.success_result(
                tool_id=self.tool_id,
                result={
                    "images": images,
                    "model": validated.model,
                    "provider": "huggingface",
                    "mode": validated.mode,
                    "num_inference_steps": validated.num_inference_steps,
                    "seed": validated.seed,
                    "cost_usd": 0.0,  # HuggingFace inference API is free tier
                    "generation_time_ms": gen_time,
                    "success": True,
                },
            )

    async def _run_local(
        self, validated: StableDiffusionPipelineInput, start: float
    ) -> ToolResult:
        """Run inference via local Automatic1111/ComfyUI API."""
        url = f"{LOCAL_SD_ENDPOINT}/sdapi/v1/txt2img"

        body: dict[str, Any] = {
            "prompt": validated.prompt,
            "negative_prompt": validated.negative_prompt or "",
            "width": validated.width,
            "height": validated.height,
            "steps": validated.num_inference_steps,
            "cfg_scale": validated.guidance_scale,
            "batch_size": validated.num_images,
            "sampler_name": validated.scheduler,
        }

        if validated.seed is not None:
            body["seed"] = validated.seed
        else:
            body["seed"] = -1

        if validated.mode == "img2img" and validated.init_image_url:
            url = f"{LOCAL_SD_ENDPOINT}/sdapi/v1/img2img"
            body["init_images"] = [validated.init_image_url]
            body["denoising_strength"] = validated.denoising_strength

        async with httpx.AsyncClient(timeout=SD_TIMEOUT) as client:
            resp = await client.post(url, json=body)
            resp.raise_for_status()
            data = resp.json()

            images = []
            for i, img_b64 in enumerate(data.get("images", [])):
                img_bytes = base64.b64decode(img_b64)
                image_entry: dict[str, Any] = {
                    "index": i,
                    "width": validated.width,
                    "height": validated.height,
                }

                if validated.save_to_storage:
                    path = self._save_image(img_bytes, validated.model, i)
                    image_entry["local_path"] = path
                else:
                    image_entry["b64_json"] = img_b64[:200] + "..."

                images.append(image_entry)

            gen_time = int((time.monotonic() - start) * 1000)
            return ToolResult.success_result(
                tool_id=self.tool_id,
                result={
                    "images": images,
                    "model": validated.model,
                    "provider": "local",
                    "mode": validated.mode,
                    "num_inference_steps": validated.num_inference_steps,
                    "seed": body.get("seed"),
                    "cost_usd": 0.0,
                    "generation_time_ms": gen_time,
                    "success": True,
                },
            )

    async def _process_output_images(
        self,
        output_urls: list[str],
        validated: StableDiffusionPipelineInput,
        start: float,
    ) -> list[dict[str, Any]]:
        """Download and process output images from URLs."""
        images = []
        async with httpx.AsyncClient(timeout=120) as client:
            for i, url in enumerate(output_urls):
                image_entry: dict[str, Any] = {"index": i, "url": str(url)}
                if validated.save_to_storage:
                    try:
                        dl_resp = await client.get(str(url), follow_redirects=True)
                        dl_resp.raise_for_status()
                        path = self._save_image(dl_resp.content, validated.model, i)
                        image_entry["local_path"] = path
                        image_entry["file_size_bytes"] = len(dl_resp.content)
                    except Exception as e:
                        logger.warning("Failed to download image %d: %s", i, e)
                images.append(image_entry)
        return images

    @staticmethod
    def _save_image(image_data: bytes, model: str, index: int) -> str:
        """Save image bytes to local storage with metadata sidecar."""
        os.makedirs(SD_STORAGE_DIR, exist_ok=True)
        digest = hashlib.sha256(image_data).hexdigest()[:16]
        model_slug = model.replace("/", "_").replace(":", "_")
        filename = f"sd_{model_slug}_{index}_{digest}.png"
        path = os.path.join(SD_STORAGE_DIR, filename)
        with open(path, "wb") as f:
            f.write(image_data)

        sidecar = {
            "model": model,
            "index": index,
            "digest": digest,
            "file_size": len(image_data),
        }
        sidecar_path = path + ".meta.json"
        with open(sidecar_path, "w") as f:
            json.dump(sidecar, f, indent=2)

        return path


register_tool(StableDiffusionPipelineTool())
