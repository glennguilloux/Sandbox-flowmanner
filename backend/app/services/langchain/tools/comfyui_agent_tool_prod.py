"""
LangChain Tool: ComfyUI Agent - Production Ready
Generate images and 3D models through natural language

Production Features:
- Connection pooling with requests.Session
- Retry logic with exponential backoff
- Structured logging
- Environment variable validation
- Custom exceptions
- Timeout handling
"""

import json
import logging
import os
import time
from typing import Any

import requests
from pydantic import BaseModel, Field, validator
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# Configure logging
logger = logging.getLogger(__name__)

# ==================== CONFIGURATION ====================


class ComfyUIConfig:
    """Configuration for ComfyUI client"""

    BASE_URL = os.getenv("COMFYUI_URL", "http://comfyui-3d:8188")
    API_KEY = os.getenv("COMFYUI_API_KEY", "")
    TIMEOUT = int(os.getenv("COMFYUI_TIMEOUT", "60"))
    MAX_RETRIES = int(os.getenv("COMFYUI_MAX_RETRIES", "3"))
    RETRY_DELAY = int(os.getenv("COMFYUI_RETRY_DELAY", "1"))

    # Validate on startup
    @classmethod
    def validate(cls):
        """Validate configuration"""
        errors = []

        if not cls.BASE_URL:
            errors.append("COMFYUI_URL is not set")

        if cls.TIMEOUT < 1:
            errors.append("COMFYUI_TIMEOUT must be positive")

        if cls.MAX_RETRIES < 0:
            errors.append("COMFYUI_MAX_RETRIES must be non-negative")

        if errors:
            logger.error(f"ComfyUI configuration errors: {errors}")
            raise ValueError(f"Invalid configuration: {', '.join(errors)}")

        logger.info(
            f"ComfyUI config validated - URL: {cls.BASE_URL}, Timeout: {cls.TIMEOUT}s"
        )


# Validate on import
try:
    ComfyUIConfig.validate()
except ValueError as e:
    logger.warning(f"ComfyUI configuration issue: {e}")

# ==================== CUSTOM EXCEPTIONS ====================


class ComfyUIError(Exception):
    """Base exception for ComfyUI operations"""

    pass


class ComfyUIConnectionError(ComfyUIError):
    """Connection to ComfyUI failed"""

    pass


class ComfyUITimeoutError(ComfyUIError):
    """ComfyUI operation timed out"""

    pass


class ComfyUIGenerationError(ComfyUIError):
    """Image generation failed"""

    pass


# ==================== VALIDATION MODELS ====================


class ComfyUIRequest(BaseModel):
    """Request model for ComfyUI operations with validation"""

    prompt: str = Field(
        ...,
        description="Natural language description of what to generate",
        min_length=1,
        max_length=1000,
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

    @validator("workflow_type")
    def validate_workflow_type(cls, v):
        allowed = ["hero-background", "product-shot", "3d-model", "general"]
        if v not in allowed:
            raise ValueError(f"Invalid workflow_type: {v}. Must be one of {allowed}")
        return v

    @validator("style")
    def validate_style(cls, v):
        allowed = ["modern", "minimal", "dark", "vibrant", "professional"]
        if v not in allowed:
            raise ValueError(f"Invalid style: {v}. Must be one of {allowed}")
        return v

    @validator("resolution")
    def validate_resolution(cls, v):
        try:
            parts = v.split("x")
            if len(parts) != 2:
                raise ValueError
            width = int(parts[0])
            height = int(parts[1])
            if width < 1 or height < 1:
                raise ValueError
        except:
            raise ValueError(
                f"Invalid resolution format: {v}. Use WIDTHxHEIGHT (e.g., 1920x1080)"
            )
        return v


class ComfyUIResponse(BaseModel):
    """Response model for ComfyUI operations"""

    success: bool
    message: str
    image_url: str | None = None
    workflow_id: str | None = None
    metadata: dict[str, Any] | None = None
    error: str | None = None


# ==================== HTTP CLIENT WITH POOLING ====================


class HTTPClient:
    """HTTP client with connection pooling and retry logic"""

    def __init__(self, base_url: str, timeout: int = 30, max_retries: int = 3):
        self.base_url = base_url
        self.timeout = timeout

        # Create session with connection pooling
        self.session = requests.Session()

        # Configure retry strategy
        retry_strategy = Retry(
            total=max_retries,
            backoff_factor=ComfyUIConfig.RETRY_DELAY,  # Exponential backoff
            status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods=["HEAD", "GET", "POST", "PUT", "DELETE", "OPTIONS"],
        )

        # Mount adapter with retry strategy
        adapter = HTTPAdapter(
            max_retries=retry_strategy, pool_connections=10, pool_maxsize=10
        )
        self.session.mount("http://", adapter)
        self.session.mount("https://", adapter)

        logger.info(
            f"HTTP client initialized - base_url: {base_url}, timeout: {timeout}s, retries: {max_retries}"
        )

    def get(self, endpoint: str, params: dict | None = None) -> requests.Response:
        """GET request with retry logic"""
        url = f"{self.base_url}{endpoint}"
        try:
            response = self.session.get(url, params=params, timeout=self.timeout)
            response.raise_for_status()
            return response
        except requests.exceptions.Timeout:
            logger.error(f"GET timeout: {url}")
            raise ComfyUITimeoutError(
                f"Request to {url} timed out after {self.timeout}s"
            )
        except requests.exceptions.ConnectionError:
            logger.error(f"GET connection error: {url}")
            raise ComfyUIConnectionError(f"Cannot connect to {url}")
        except Exception as e:
            logger.error(f"GET error: {url} - {e}")
            raise ComfyUIError(f"GET request failed: {e}")

    def post(
        self, endpoint: str, json_data: dict | None = None
    ) -> requests.Response:
        """POST request with retry logic"""
        url = f"{self.base_url}{endpoint}"
        try:
            response = self.session.post(url, json=json_data, timeout=self.timeout)
            response.raise_for_status()
            return response
        except requests.exceptions.Timeout:
            logger.error(f"POST timeout: {url}")
            raise ComfyUITimeoutError(
                f"Request to {url} timed out after {self.timeout}s"
            )
        except requests.exceptions.ConnectionError:
            logger.error(f"POST connection error: {url}")
            raise ComfyUIConnectionError(f"Cannot connect to {url}")
        except Exception as e:
            logger.error(f"POST error: {url} - {e}")
            raise ComfyUIError(f"POST request failed: {e}")

    def close(self):
        """Close session"""
        if self.session:
            self.session.close()
            logger.info("HTTP session closed")


# ==================== COMFYUI CLIENT ====================


class ComfyUIClient:
    """Production-ready ComfyUI client"""

    def __init__(self):
        self.config = ComfyUIConfig
        self.http_client = HTTPClient(
            base_url=self.config.BASE_URL,
            timeout=self.config.TIMEOUT,
            max_retries=self.config.MAX_RETRIES,
        )
        logger.info(f"ComfyUIClient initialized for {self.config.BASE_URL}")

    def check_health(self) -> bool:
        """Check if ComfyUI is available"""
        try:
            response = self.http_client.get("/", params=None)
            return response.status_code == 200
        except Exception as e:
            logger.warning(f"Health check failed: {e}")
            return False

    def generate_image(self, request: ComfyUIRequest) -> dict:
        """Generate image using ComfyUI with full error handling"""
        logger.info(
            f"Starting image generation - type: {request.workflow_type}, style: {request.style}"
        )

        try:
            # Health check
            if not self.check_health():
                return {
                    "success": False,
                    "error": f"ComfyUI is not responding at {self.config.BASE_URL}",
                    "note": "Make sure ComfyUI is running and accessible",
                }

            # Build workflow
            workflow = self._build_workflow(request)
            logger.debug(f"Workflow built for {request.workflow_type}")

            # Send to ComfyUI
            response = self.http_client.post("/prompt", json_data={"prompt": workflow})
            result = response.json()
            prompt_id = result.get("prompt_id")

            logger.info(f"Workflow submitted - prompt_id: {prompt_id}")

            # Wait for completion
            return self._wait_for_image(prompt_id, request)

        except ComfyUIConnectionError as e:
            logger.error(f"Connection error during generation: {e}")
            return {
                "success": False,
                "error": str(e),
                "note": "Check if ComfyUI service is running",
            }
        except ComfyUITimeoutError as e:
            logger.error(f"Timeout during generation: {e}")
            return {
                "success": False,
                "error": str(e),
                "note": "Generation took too long, try with simpler prompt",
            }
        except Exception as e:
            logger.error(f"Unexpected error during generation: {e}", exc_info=True)
            return {
                "success": False,
                "error": f"Generation failed: {e!s}",
                "note": "Check ComfyUI service status and model availability",
            }

    def _build_workflow(self, request: ComfyUIRequest) -> dict:
        """Build ComfyUI workflow based on request"""
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
        available_models = {
            "3d-model": "hy3dgen/sd3_medium_incl_clanks.safetensors",
            "hero-background": "hy3dgen/sd3_medium_incl_clanks.safetensors",
            "product-shot": "hy3dgen/sd3_medium_incl_clanks.safetensors",
            "general": "hy3dgen/sd3_medium_incl_clanks.safetensors",
        }
        return available_models.get(
            workflow_type, "hy3dgen/sd3_medium_incl_clanks.safetensors"
        )

    def _get_width(self, resolution: str) -> int:
        """Extract width from resolution"""
        try:
            return int(resolution.split("x")[0])
        except:
            logger.warning(f"Invalid resolution format, using default: {resolution}")
            return 1920

    def _get_height(self, resolution: str) -> int:
        """Extract height from resolution"""
        try:
            return int(resolution.split("x")[1])
        except:
            logger.warning(f"Invalid resolution format, using default: {resolution}")
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

    def _wait_for_image(self, prompt_id: str, request: ComfyUIRequest) -> dict:
        """Wait for image generation to complete with timeout handling"""
        start_time = time.time()
        timeout = self.config.TIMEOUT

        logger.info(
            f"Waiting for completion - prompt_id: {prompt_id}, timeout: {timeout}s"
        )

        while time.time() - start_time < timeout:
            try:
                response = self.http_client.get(f"/history/{prompt_id}")
                history = response.json()

                if prompt_id in history:
                    outputs = history[prompt_id].get("output", {})

                    # Find image in outputs
                    for node_output in outputs.values():
                        if "images" in node_output:
                            image = node_output["images"][0]
                            image_url = self._get_image_url(image)

                            logger.info(
                                f"Image generated successfully - prompt_id: {prompt_id}"
                            )
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

            except ComfyUIError:
                # Retry on transient errors
                time.sleep(2)
            except Exception as e:
                logger.error(f"Error waiting for image: {e}")
                time.sleep(2)

        logger.warning(f"Generation timed out - prompt_id: {prompt_id}")
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
            return (
                f"{self.config.BASE_URL}/view?filename={filename}&subfolder={subfolder}"
            )
        else:
            return f"{self.config.BASE_URL}/view?filename={filename}"

    def close(self):
        """Close HTTP client"""
        self.http_client.close()


# ==================== CONVENIENCE FUNCTIONS ====================


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
        logger.error(f"generate_comfyui_image failed: {e}")
        return json.dumps({"success": False, "error": str(e)}, indent=2)
    finally:
        client.close()


def generate_hero_background(prompt: str, style: str = "modern") -> str:
    """
    Generate a hero background image (1920x1080).

    Use this for: website headers, banners, presentations
    """
    return generate_comfyui_image(
        prompt=prompt,
        workflow_type="hero-background",
        style=style,
        resolution="1920x1080",
    )


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
