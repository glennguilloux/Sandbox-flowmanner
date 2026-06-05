"""
LangChain Tool: ComfyUI Agent
Generate images and 3D models through natural language
"""

import json
import logging
import os
import time
from typing import Any

import requests
from pydantic import BaseModel, Field


class ComfyUIRequest(BaseModel):
    """Request model for ComfyUI operations"""

    prompt: str = Field(
        ..., description="Natural language description of what to generate"
    )
    workflow_type: str = Field(
        "hero-background",
        description="Type: hero-background, product-shot, 3d-model, general",
    )
    style: str = Field(
        "modern", description="Style: modern, minimal, dark, vibrant, professional"
    )
    resolution: str = Field(
        "1920x1080", description="Resolution: 1920x1080, 1024x1024, etc"
    )
    seed: int | None = Field(None, description="Seed for reproducibility")


class ComfyUIResponse(BaseModel):
    """Response model for ComfyUI operations"""

    success: bool
    message: str
    image_url: str | None = None
    workflow_id: str | None = None
    metadata: dict[str, Any] | None = None


logger = logging.getLogger(__name__)


class ComfyUIClient:
    """Client for ComfyUI API"""

    def __init__(self):
        self.base_url = os.getenv("COMFYUI_URL", "http://comfyui-3d:8188")
        self.api_key = os.getenv("COMFYUI_API_KEY", "")

    def generate_image(self, request: ComfyUIRequest) -> dict:
        """Generate image using ComfyUI"""
        try:
            # Check if ComfyUI is available
            try:
                health_check = requests.get(f"{self.base_url}/", timeout=5)
                if health_check.status_code != 200:
                    return {
                        "success": False,
                        "error": f"ComfyUI is not responding at {self.base_url}. Status: {health_check.status_code}",
                        "note": "Make sure ComfyUI is running and accessible",
                    }
            except requests.exceptions.ConnectionError:
                return {
                    "success": False,
                    "error": f"Cannot connect to ComfyUI at {self.base_url}",
                    "note": "Check if ComfyUI service is running and the URL is correct",
                }

            # Build workflow based on type
            workflow = self._build_workflow(request)

            # Send to ComfyUI
            response = requests.post(
                f"{self.base_url}/prompt", json={"prompt": workflow}, timeout=60
            )

            if response.status_code != 200:
                return {
                    "success": False,
                    "error": f"ComfyUI returned error: {response.status_code} {response.reason}",
                    "details": response.text[:500] if response.text else "No details",
                    "note": "This may be due to missing models or incorrect workflow format",
                }

            result = response.json()
            prompt_id = result.get("prompt_id")

            # Wait for completion
            return self._wait_for_image(prompt_id, request)

        except Exception as e:
            return {
                "success": False,
                "error": f"ComfyUI generation failed: {e!s}",
                "note": "Check ComfyUI service status and model availability",
            }

    def _build_workflow(self, request: ComfyUIRequest) -> dict:
        """Build ComfyUI workflow based on request"""

        # Base workflow structure
        workflow = {
            "3": {
                "class_type": "KSampler",
                "inputs": {
                    "seed": request.seed or int(time.time()),
                    "steps": 25 if request.workflow_type == "hero-background" else 30,
                    "cfg": 7.5,
                    "sampler_name": "dpmpp_2m",
                    "scheduler": "normal",
                    "denoise": 1.0,
                    "model": ["4", 0],
                    "positive": ["7", 0],
                    "negative": ["8", 0],
                    "latent_image": ["5", 0],
                },
            },
            "4": {
                "class_type": "CheckpointLoaderSimple",
                "inputs": {"ckpt_name": self._get_model(request.workflow_type)},
            },
            "5": {
                "class_type": "EmptyLatentImage",
                "inputs": {
                    "width": self._get_width(request.resolution),
                    "height": self._get_height(request.resolution),
                    "batch_size": 1,
                },
            },
            "6": {
                "class_type": "CLIPTextEncode",
                "inputs": {"text": self._build_prompt(request), "clip": ["4", 1]},
            },
            "7": {
                "class_type": "CLIPTextEncode",
                "inputs": {
                    "text": self._build_positive_prompt(request),
                    "clip": ["4", 1],
                },
            },
            "8": {
                "class_type": "CLIPTextEncode",
                "inputs": {
                    "text": self._build_negative_prompt(request),
                    "clip": ["4", 1],
                },
            },
            "9": {
                "class_type": "VAEDecode",
                "inputs": {"samples": ["3", 0], "vae": ["4", 2]},
            },
            "10": {
                "class_type": "SaveImage",
                "inputs": {
                    "images": ["9", 0],
                    "filename_prefix": f"ai_gen_{int(time.time())}",
                },
            },
        }

        return workflow

    def _get_model(self, workflow_type: str) -> str:
        """Get appropriate model for workflow type"""
        # For this ComfyUI instance (3D-focused), use available models
        # Check what's actually available
        available_models = {
            "3d-model": "hy3dgen/sd3_medium_incl_clanks.safetensors",  # 3D model
            "hero-background": "hy3dgen/sd3_medium_incl_clanks.safetensors",  # Fallback
            "product-shot": "hy3dgen/sd3_medium_incl_clanks.safetensors",  # Fallback
            "general": "hy3dgen/sd3_medium_incl_clanks.safetensors",
        }
        return available_models.get(
            workflow_type, "hy3dgen/sd3_medium_incl_clanks.safetensors"
        )

    def _get_width(self, resolution: str) -> int:
        """Extract width from resolution"""
        try:
            return int(resolution.split("x")[0])
        except Exception:
            logger.debug("Invalid resolution format, using default width: %s", resolution)
            return 1920

    def _get_height(self, resolution: str) -> int:
        """Extract height from resolution"""
        try:
            return int(resolution.split("x")[1])
        except Exception:
            logger.debug("Invalid resolution format, using default height: %s", resolution)
            return 1080

    def _build_prompt(self, request: ComfyUIRequest) -> str:
        """Build base prompt from user input"""
        return request.prompt

    def _build_positive_prompt(self, request: ComfyUIRequest) -> str:
        """Build positive prompt with style and quality tags"""
        style_tags = {
            "modern": "modern, clean, contemporary",
            "minimal": "minimalist, simple, clean",
            "dark": "dark mode, dark theme, moody",
            "vibrant": "vibrant, colorful, rich",
            "professional": "professional, high quality, polished",
        }

        style = style_tags.get(request.style, "")

        # Workflow-specific enhancements
        if request.workflow_type == "hero-background":
            return f"{request.prompt}, {style}, hero background, cinematic, high quality, 4k"
        elif request.workflow_type == "product-shot":
            return f"{request.prompt}, {style}, product photography, studio lighting, professional, high detail"
        elif request.workflow_type == "3d-model":
            return f"{request.prompt}, {style}, 3D render, 3D model, detailed, high quality, 3D art"
        else:
            return f"{request.prompt}, {style}, high quality, detailed"

    def _build_negative_prompt(self, request: ComfyUIRequest) -> str:
        """Build negative prompt"""
        base_negative = (
            "blurry, low quality, watermark, text, signature, ugly, deformed, distorted"
        )

        if request.workflow_type == "hero-background":
            return f"{base_negative}, people, faces, text overlay"
        elif request.workflow_type == "product-shot":
            return f"{base_negative}, bad lighting, shadows, clutter"
        elif request.workflow_type == "3d-model":
            return f"{base_negative}, 2D, flat, cartoon, drawing"
        else:
            return base_negative

    def _wait_for_image(
        self, prompt_id: str, request: ComfyUIRequest, timeout: int = 120
    ) -> dict:
        """Wait for image generation to complete"""
        start_time = time.time()

        while time.time() - start_time < timeout:
            try:
                # Check history
                response = requests.get(
                    f"{self.base_url}/history/{prompt_id}", timeout=5
                )
                response.raise_for_status()
                history = response.json()

                if prompt_id in history:
                    outputs = history[prompt_id].get("output", {})

                    # Find image in outputs
                    for node_output in outputs.values():
                        if "images" in node_output:
                            image = node_output["images"][0]

                            # Get image URL
                            image_url = self._get_image_url(image)

                            return {
                                "success": True,
                                "message": f"Generated {request.workflow_type} with {request.style} style",
                                "image_url": image_url,
                                "workflow_id": prompt_id,
                                "metadata": {
                                    "workflow_type": request.workflow_type,
                                    "style": request.style,
                                    "resolution": request.resolution,
                                    "seed": request.seed,
                                },
                            }

                time.sleep(2)

            except Exception:
                time.sleep(2)

        return {
            "success": False,
            "message": f"Generation timed out after {timeout} seconds",
            "workflow_id": prompt_id,
        }

    def _get_image_url(self, image: dict) -> str:
        """Build image URL from ComfyUI output"""
        filename = image.get("filename")
        subfolder = image.get("subfolder", "")

        if subfolder:
            return f"{self.base_url}/view?filename={filename}&subfolder={subfolder}"
        else:
            return f"{self.base_url}/view?filename={filename}"


def generate_comfyui_image(
    prompt: str,
    workflow_type: str = "hero-background",
    style: str = "modern",
    resolution: str = "1920x1080",
    seed: int | None = None,
) -> str:
    """
    Generate images or 3D models using ComfyUI through natural language.

    Parameters:
    - prompt: Natural language description of what to generate
    - workflow_type: hero-background, product-shot, 3d-model, or general
    - style: modern, minimal, dark, vibrant, professional
    - resolution: 1920x1080, 1024x1024, etc
    - seed: Optional seed for reproducibility

    Examples:
    - "Generate tech hero background" -> generate_comfyui_image("tech hero background")
    - "Create product shot of smartphone" -> generate_comfyui_image("smartphone", "product-shot")
    - "Make 3D model of car" -> generate_comfyui_image("sports car", "3d-model", "vibrant")

    Returns: JSON string with image URL and metadata
    """
    client = ComfyUIClient()

    try:
        request = ComfyUIRequest(
            prompt=prompt,
            workflow_type=workflow_type,
            style=style,
            resolution=resolution,
            seed=seed,
        )

        result = client.generate_image(request)
        return json.dumps(result, indent=2)

    except Exception as e:
        return json.dumps({"success": False, "error": str(e)}, indent=2)


# Convenience functions for common operations
# Note: These are plain functions, not decorated with @tool
# They can be called directly and use ComfyUIClient directly


def generate_hero_background(prompt: str, style: str = "modern") -> str:
    """
    Generate a hero background image (1920x1080).

    Use this for: website headers, banners, presentations
    """
    client = ComfyUIClient()
    request = ComfyUIRequest(
        prompt=prompt,
        workflow_type="hero-background",
        style=style,
        resolution="1920x1080",
    )
    try:
        result = client.generate_image(request)
        return json.dumps(result, indent=2)
    except Exception as e:
        return json.dumps({"success": False, "error": str(e)}, indent=2)


def generate_product_shot(product: str, style: str = "professional") -> str:
    """
    Generate a product shot (1024x1024).

    Use this for: e-commerce, product photos, catalogs

    Example:
    - "Generate product shot of smartphone" -> generate_product_shot("smartphone")
    - "Create photo of headphones" -> generate_product_shot("wireless headphones", "modern")
    """
    return generate_comfyui_image(
        prompt=product,
        workflow_type="product-shot",
        style=style,
        resolution="1024x1024",
    )


def generate_3d_model(description: str, style: str = "modern") -> str:
    """
    Generate a 3D model image (1024x1024).

    Use this for: 3D art, game assets, visualizations

    Example:
    - "Generate 3D model of smartphone" -> generate_3d_model("smartphone")
    - "Create 3D car model" -> generate_3d_model("sports car", "vibrant")
    """
    return generate_comfyui_image(
        prompt=description,
        workflow_type="3d-model",
        style=style,
        resolution="1024x1024",
    )
