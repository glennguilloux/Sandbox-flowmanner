"""
Training Tasks
Celery tasks for LoRA adapter training and dataset generation
"""

import json
import logging
import os
from datetime import UTC, datetime
from typing import Any

from celery import shared_task
from celery.result import AsyncResult

logger = logging.getLogger(__name__)

# Redis for progress streaming
import redis

REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379")
redis_client = redis.from_url(REDIS_URL)


def publish_progress(model_id: str, event: str, data: dict[str, Any]):
    """Publish training progress to Redis channel"""
    channel = f"training:{model_id}"
    message = json.dumps(
        {"event": event, "timestamp": datetime.now(UTC).isoformat(), "data": data}
    )
    redis_client.publish(channel, message)
    logger.info(f"Published {event} to {channel}")


@shared_task(name="training.check_gpu_status", bind=True)
def check_gpu_status_task(self) -> dict[str, Any]:
    """
    Check GPU status for training availability

    Returns:
        Dict with GPU status info
    """
    try:
        from app.services.gpu_manager import get_gpu_manager

        gpu_manager = get_gpu_manager()
        status = gpu_manager.get_status()

        return status.to_dict()

    except Exception as e:
        logger.error(f"Error checking GPU status: {e}")
        return {
            "error": str(e),
            "cuda_available": False,
        }


@shared_task(name="training.can_start_training", bind=True)
def can_start_training_task(self, min_vram_gb: float = 10.0) -> dict[str, Any]:
    """
    Check if training can start

    Args:
        min_vram_gb: Minimum free VRAM required

    Returns:
        Dict with can_train status
    """
    try:
        from app.services.gpu_manager import get_gpu_manager

        gpu_manager = get_gpu_manager()
        can_train = gpu_manager.can_start_training(min_vram_gb)
        status = gpu_manager.get_status()

        return {
            "can_train": can_train,
            "training_gpu_id": gpu_manager.get_training_gpu_id(),
            "free_vram_gb": (
                status.training_gpu.free_vram_gb if status.training_gpu else 0
            ),
            "min_required_vram_gb": min_vram_gb,
            "message": status.message,
        }

    except Exception as e:
        logger.error(f"Error checking training availability: {e}")
        return {
            "can_train": False,
            "error": str(e),
        }


@shared_task(name="training.generate_dataset", bind=True)
def generate_dataset_task(
    self,
    collection_id: str,
    num_samples: int = 500,
    model: str = "qwen3",
    base_model: str = "Qwen/Qwen2.5-0.5B-Instruct",
) -> dict[str, Any]:
    """
    Generate training dataset from a RAG collection

    Args:
        collection_id: Qdrant collection ID
        num_samples: Target number of samples
        model: Model to use for Q&A generation
        base_model: Base model for the adapter

    Returns:
        Dataset generation result
    """
    logger.info(f"Starting dataset generation for collection: {collection_id}")

    # Publish start event
    publish_progress(
        collection_id,
        "dataset_generation_started",
        {
            "collection_id": collection_id,
            "num_samples": num_samples,
        },
    )

    try:
        from app.services.dataset_generator import get_dataset_generator

        # Update task state
        self.update_state(
            state="PROGRESS", meta={"stage": "loading_documents", "progress": 0}
        )

        generator = get_dataset_generator()

        # Generate dataset
        import asyncio

        result = asyncio.run(
            generator.generate_from_collection(
                collection_id=collection_id,
                num_samples=num_samples,
                model=model,
                base_model=base_model,
            )
        )

        # Publish completion
        publish_progress(
            collection_id, "dataset_generation_completed", result.to_dict()
        )

        logger.info(f"Dataset generation completed: {result.file_path}")
        return result.to_dict()

    except Exception as e:
        logger.error(f"Dataset generation failed: {e}")
        publish_progress(
            collection_id,
            "dataset_generation_error",
            {
                "error": str(e),
                "collection_id": collection_id,
            },
        )
        raise


@shared_task(name="training.train_adapter", bind=True)
def train_adapter_task(
    self,
    model_id: str,
    dataset_path: str,
    base_model_key: str = "tiny",
    epochs: int = 3,
    lora_rank: int = 16,
) -> dict[str, Any]:
    """
    Train a LoRA adapter

    This task is designed to be forwarded to the training container.
    The actual training happens in the isolated training worker.

    Args:
        model_id: Unique identifier for the adapter
        dataset_path: Path to the training dataset
        base_model_key: Key for base model (tiny/small/medium)
        epochs: Number of training epochs
        lora_rank: LoRA rank

    Returns:
        Training metrics
    """
    logger.info(f"Starting training task for model: {model_id}")

    # Publish start event
    publish_progress(
        model_id,
        "training_started",
        {
            "model_id": model_id,
            "base_model_key": base_model_key,
            "epochs": epochs,
            "lora_rank": lora_rank,
        },
    )

    try:
        # Check if training can start
        from app.services.gpu_manager import get_gpu_manager

        gpu_manager = get_gpu_manager()
        if not gpu_manager.can_start_training():
            raise Exception("Insufficient GPU resources for training")

        # Update task state
        self.update_state(
            state="PROGRESS", meta={"stage": "initializing", "progress": 0}
        )

        publish_progress(
            model_id,
            "progress",
            {"stage": "initializing", "progress": 0, "message": "Starting training..."},
        )

        # The actual training is handled by the training container
        # This task coordinates and tracks progress

        # For now, we'll call the training script directly
        # In production, this would be a Celery task sent to the training queue

        import subprocess

        training_script = "/app/train_lora.py"
        if not os.path.exists(training_script):
            # Training script is in the training container
            # We need to trigger it via Celery or API call
            logger.info(
                "Training script not in backend, forwarding to training container"
            )

            # For now, return a placeholder
            # In production, use Celery's send_task to route to training queue
            return {
                "model_id": model_id,
                "status": "queued",
                "message": "Training task forwarded to training container",
            }

        # Run training script
        cmd = [
            "python",
            training_script,
            "--model-id",
            model_id,
            "--dataset",
            dataset_path,
            "--base-model",
            base_model_key,
            "--epochs",
            str(epochs),
            "--lora-rank",
            str(lora_rank),
        ]

        logger.info(f"Running: {' '.join(cmd)}")

        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=4 * 60 * 60,  # 4 hour timeout
        )

        if result.returncode != 0:
            raise Exception(f"Training failed: {result.stderr}")

        # Parse training metrics
        metrics = json.loads(result.stdout)

        # Publish completion
        publish_progress(model_id, "training_completed", metrics)

        logger.info(f"Training completed for model: {model_id}")
        return metrics

    except Exception as e:
        logger.error(f"Training failed for model {model_id}: {e}")
        publish_progress(
            model_id,
            "training_error",
            {
                "error": str(e),
                "model_id": model_id,
            },
        )
        raise


@shared_task(name="training.export_gguf", bind=True)
def export_gguf_task(
    self,
    adapter_path: str,
    output_path: str = None,
    quantization: str = "q4_k_m",
) -> dict[str, Any]:
    """
    Export trained adapter to GGUF format

    Args:
        adapter_path: Path to trained adapter
        output_path: Output directory for GGUF file
        quantization: Quantization method

    Returns:
        Export result
    """
    logger.info(f"Starting GGUF export for adapter: {adapter_path}")

    try:
        import subprocess

        export_script = "/app/export_gguf.py"

        cmd = [
            "python",
            export_script,
            "--adapter",
            adapter_path,
            "--quantization",
            quantization,
        ]

        if output_path:
            cmd.extend(["--output", output_path])

        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=30 * 60,  # 30 min timeout
        )

        if result.returncode != 0:
            raise Exception(f"GGUF export failed: {result.stderr}")

        metrics = json.loads(result.stdout)

        logger.info(f"GGUF export completed: {metrics.get('gguf_path')}")
        return metrics

    except Exception as e:
        logger.error(f"GGUF export failed: {e}")
        raise


@shared_task(name="training.validate_dataset", bind=True)
def validate_dataset_task(self, dataset_path: str) -> dict[str, Any]:
    """
    Validate a training dataset

    Args:
        dataset_path: Path to the dataset JSON file

    Returns:
        Validation result
    """
    MIN_SAMPLES = 100
    MIN_RESPONSE_LENGTH = 50

    try:
        with open(dataset_path, "r") as f:
            data = json.load(f)

        if isinstance(data, list):
            samples = data
        elif isinstance(data, dict) and "train" in data:
            samples = data["train"]
        else:
            samples = [data]

        # Validate structure
        valid_samples = 0
        for sample in samples:
            if "instruction" in sample and "output" in sample:
                if len(sample.get("output", "")) >= MIN_RESPONSE_LENGTH:
                    valid_samples += 1

        return {
            "valid": valid_samples >= MIN_SAMPLES,
            "total_samples": len(samples),
            "valid_samples": valid_samples,
            "min_required": MIN_SAMPLES,
            "message": (
                "Dataset valid"
                if valid_samples >= MIN_SAMPLES
                else f"Need at least {MIN_SAMPLES} valid samples"
            ),
        }

    except Exception as e:
        return {"valid": False, "error": str(e)}


@shared_task(name="training.get_training_progress", bind=True)
def get_training_progress_task(self, model_id: str) -> dict[str, Any]:
    """
    Get training progress for a model

    Args:
        model_id: Model ID to check progress for

    Returns:
        Progress info from Redis
    """
    try:
        # Check Redis for latest progress
        channel = f"training:{model_id}"

        # Get last message from channel
        # Note: Redis pub/sub doesn't store history, so we'd need to
        # implement a separate progress store for persistence

        # For now, check task result
        task_id = redis_client.get(f"training_task:{model_id}")
        if task_id:
            result = AsyncResult(task_id.decode(), app=self._app)
            return {
                "task_id": task_id.decode(),
                "status": result.status,
                "result": result.result if result.ready() else None,
            }

        return {
            "model_id": model_id,
            "status": "unknown",
            "message": "No training task found for this model",
        }

    except Exception as e:
        return {
            "model_id": model_id,
            "status": "error",
            "error": str(e),
        }
