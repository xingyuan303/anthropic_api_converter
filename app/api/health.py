"""
Health check endpoint.

Provides application health status and readiness checks.
"""
import logging
import time
from datetime import datetime

from fastapi import APIRouter, status
from fastapi.responses import JSONResponse

from app.core.config import settings

logger = logging.getLogger(__name__)

router = APIRouter()

# Store application start time
START_TIME = time.time()


@router.get(
    "/health",
    status_code=status.HTTP_200_OK,
    summary="Health check",
    description="Check application health and readiness.",
    tags=["monitoring"],
)
async def health_check():
    """
    Health check endpoint.

    Returns application health status, uptime, and configuration info.

    Returns:
        Dictionary with health status information
    """
    uptime_seconds = int(time.time() - START_TIME)

    return {
        "status": "healthy",
        "timestamp": datetime.utcnow().isoformat(),
        "uptime_seconds": uptime_seconds,
        "version": settings.app_version,
        "environment": settings.environment,
        "services": {
            "bedrock": {
                "status": "available",
                "region": settings.aws_region,
            },
            "dynamodb": {
                "status": "available",
                "region": settings.aws_region,
            },
        },
        "features": {
            "streaming": True,
            "tool_use": settings.enable_tool_use,
            "extended_thinking": settings.enable_extended_thinking,
            "document_support": settings.enable_document_support,
            "prompt_caching": settings.prompt_caching_enabled,
            "programmatic_tool_calling": settings.enable_programmatic_tool_calling,
        },
    }


@router.get(
    "/ready",
    status_code=status.HTTP_200_OK,
    summary="Readiness check",
    description="Check if application is ready to serve requests.",
    tags=["monitoring"],
)
async def readiness_check():
    """
    Readiness check endpoint.

    Used by orchestrators (Kubernetes, ECS) to determine if the application
    is ready to receive traffic.

    Returns:
        Dictionary with readiness status
    """
    # In a production system, you might check:
    # - Database connectivity
    # - AWS credentials validity
    # - Required environment variables
    # - Dependent service availability

    return {
        "status": "ready",
        "timestamp": datetime.utcnow().isoformat(),
    }


@router.get(
    "/liveness",
    status_code=status.HTTP_200_OK,
    summary="Liveness check",
    description="Check if application is alive (used by orchestrators).",
    tags=["monitoring"],
)
async def liveness_check():
    """
    Liveness check endpoint.

    Used by orchestrators to determine if the application is alive.
    Should be a lightweight check that doesn't test dependencies.

    Returns:
        Dictionary with liveness status
    """
    return {
        "status": "alive",
        "timestamp": datetime.utcnow().isoformat(),
    }


@router.get(
    "/health/ptc",
    status_code=status.HTTP_200_OK,
    summary="PTC health check",
    description="Check Programmatic Tool Calling (PTC) subsystem health.",
    tags=["monitoring"],
)
async def ptc_health_check():
    """
    PTC health check endpoint.

    Checks Docker availability and PTC subsystem status.
    Returns 200 if PTC is available, 503 if unavailable.

    Returns:
        Dictionary with PTC health status information
    """
    from app.services.ptc_service import get_ptc_service
    import os

    # Get instance identification for multi-instance deployments
    instance_id = os.environ.get('HOSTNAME', os.environ.get('COMPUTERNAME', 'unknown'))

    result = {
        "enabled": settings.enable_programmatic_tool_calling,
        "instance_id": instance_id,
        "config": {
            "sandbox_image": settings.ptc_sandbox_image,
            "session_timeout": settings.ptc_session_timeout,
            "execution_timeout": settings.ptc_execution_timeout,
            "memory_limit": settings.ptc_memory_limit,
            "network_disabled": settings.ptc_network_disabled,
        },
        "timestamp": datetime.utcnow().isoformat(),
        "multi_instance_note": "PTC sessions are instance-specific. Ensure ALB sticky sessions are enabled for multi-instance deployments.",
    }

    if not settings.enable_programmatic_tool_calling:
        result["status"] = "disabled"
        return result

    try:
        ptc_service = get_ptc_service()
        docker_available = ptc_service.is_docker_available()

        if docker_available:
            # Check if sandbox image exists, auto-pull if not
            sandbox_executor = ptc_service.sandbox_executor
            image_available = sandbox_executor.is_image_available()

            if not image_available:
                # Try to pull the image automatically
                logger.info(f"[PTC] Sandbox image not available, attempting auto-pull...")
                result["image_pull_status"] = "pulling"
                try:
                    image_available = await sandbox_executor.ensure_image_available()
                    if image_available:
                        result["image_pull_status"] = "success"
                        logger.info(f"[PTC] Auto-pull completed successfully")
                    else:
                        result["image_pull_status"] = "failed"
                        logger.warning(f"[PTC] Auto-pull failed")
                except Exception as pull_error:
                    result["image_pull_status"] = "error"
                    result["image_pull_error"] = str(pull_error)
                    logger.error(f"[PTC] Auto-pull error: {pull_error}")

            # Get active session count and session IDs (for debugging)
            try:
                active_sessions = len(sandbox_executor.active_sessions)
                session_ids = list(sandbox_executor.active_sessions.keys())[:10]  # Limit to 10 for readability
            except Exception:
                active_sessions = 0
                session_ids = []

            result["status"] = "healthy"
            result["docker"] = "connected"
            result["sandbox_image_available"] = image_available
            result["active_sessions"] = active_sessions
            result["session_ids_sample"] = session_ids  # For debugging routing issues
            result["note"] = (
                f"Instance {instance_id} has {active_sessions} active PTC session(s). "
                f"If continuation requests fail with 'session not found', verify ALB sticky sessions are enabled."
            )
            return result
        else:
            result["status"] = "unhealthy"
            result["docker"] = "unavailable"
            result["error"] = "Docker is not available"
            return JSONResponse(status_code=503, content=result)

    except Exception as e:
        logger.error(f"PTC health check failed: {e}")
        result["status"] = "unhealthy"
        result["error"] = str(e)
        return JSONResponse(status_code=503, content=result)


@router.post(
    "/api/event_logging/batch",
    status_code=status.HTTP_200_OK,
    include_in_schema=False,  # Hide from API docs
)
async def event_logging_batch():
    """
    Dummy endpoint to accept Anthropic SDK telemetry requests.

    The Anthropic Python SDK sends telemetry data to this endpoint.
    We accept and discard these requests to avoid 404 log noise.
    """
    return {"status": "ok"}
