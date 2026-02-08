"""
Authentication middleware for API key validation.

Validates API keys from request headers and attaches user information to requests.
"""
from typing import Callable

from botocore.exceptions import ClientError
from fastapi import HTTPException, Request, status
from fastapi.responses import JSONResponse
from fastapi.security import APIKeyHeader
from starlette.middleware.base import BaseHTTPMiddleware

from app.core.config import settings
from app.db.dynamodb import APIKeyManager, DynamoDBClient


# API Key header scheme
api_key_header_scheme = APIKeyHeader(
    name=settings.api_key_header,
    auto_error=False,
)


class AuthMiddleware(BaseHTTPMiddleware):
    """Middleware for API key authentication."""

    def __init__(self, app, dynamodb_client: DynamoDBClient):
        """
        Initialize auth middleware.

        Args:
            app: FastAPI application
            dynamodb_client: DynamoDB client instance
        """
        super().__init__(app)
        self.api_key_manager = APIKeyManager(dynamodb_client)

    async def dispatch(self, request: Request, call_next: Callable):
        """
        Process request and validate API key.

        Args:
            request: HTTP request
            call_next: Next middleware/handler

        Returns:
            HTTP response

        Raises:
            HTTPException: If authentication fails
        """
        # Skip authentication for health check and docs endpoints
        skip_auth_paths = ["/health", "/health/ptc", "/ready", "/liveness", "/docs", "/openapi.json", "/redoc", "/"]
        if request.url.path in skip_auth_paths:
            return await call_next(request)

        # Skip if API key is not required
        if not settings.require_api_key:
            request.state.api_key_info = None
            return await call_next(request)

        # Extract API key from header
        api_key = request.headers.get(settings.api_key_header)

        if not api_key:
            print(f"[AUTH] Missing API key for {request.url.path}")
            from fastapi.responses import JSONResponse
            return JSONResponse(
                status_code=status.HTTP_401_UNAUTHORIZED,
                content={
                    "type": "error",
                    "error": {
                        "type": "authentication_error",
                        "message": f"Missing API key in {settings.api_key_header} header",
                    },
                },
            )

        # Check master API key first (if configured)
        if settings.master_api_key and api_key == settings.master_api_key:
            request.state.api_key_info = {
                "api_key": api_key,
                "user_id": "master",
                "is_master": True,
                "rate_limit": None,  # No rate limit for master key
            }
            return await call_next(request)

        # Validate API key in DynamoDB
        try:
            api_key_info = self.api_key_manager.validate_api_key(api_key)
        except ClientError as e:
            # DynamoDB specific errors (connection issues, throttling, etc.)
            error_code = e.response.get('Error', {}).get('Code', 'Unknown')
            print(f"[ERROR] DynamoDB error during API key validation: {error_code}")
            print(f"[ERROR] Message: {str(e)}")
            return JSONResponse(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                content={
                    "type": "error",
                    "error": {
                        "type": "api_error",
                        "message": "Authentication service temporarily unavailable. Please try again in a moment.",
                    },
                },
            )
        except Exception as e:
            # Unexpected errors
            print(f"\n[ERROR] Unexpected exception during API key validation")
            print(f"[ERROR] Type: {type(e).__name__}")
            print(f"[ERROR] Message: {str(e)}")
            import traceback
            print(f"[ERROR] Traceback:\n{traceback.format_exc()}\n")
            return JSONResponse(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                content={
                    "type": "error",
                    "error": {
                        "type": "api_error",
                        "message": "Internal server error during authentication. Please contact support if this persists.",
                    },
                },
            )

        if not api_key_info:
            # Check if the key exists but is deactivated (for better error message)
            from fastapi.responses import JSONResponse
            try:
                from botocore.exceptions import ClientError
                table = self.api_key_manager.table
                response = table.get_item(Key={"api_key": api_key})
                item = response.get("Item")

                if item and not item.get("is_active", False):
                    # Key exists but is deactivated - provide specific reason
                    deactivated_reason = item.get("deactivated_reason")

                    if deactivated_reason == "budget_exceeded":
                        budget_used = float(item.get("budget_used_mtd", 0))
                        monthly_budget = float(item.get("monthly_budget", 0))
                        print(f"[AUTH] API key deactivated due to budget exceeded: {api_key[:20]}... (Used: ${budget_used:.2f} / Limit: ${monthly_budget:.2f})")

                        return JSONResponse(
                            status_code=status.HTTP_402_PAYMENT_REQUIRED,
                            content={
                                "type": "error",
                                "error": {
                                    "type": "budget_exceeded_error",
                                    "message": f"API key has been deactivated because the monthly budget limit (${monthly_budget:.2f}) has been exceeded. Current usage: ${budget_used:.2f}. The key will automatically reactivate at the start of next month.",
                                },
                            },
                        )
                    elif deactivated_reason:
                        # Other deactivation reasons
                        print(f"[AUTH] API key deactivated ({deactivated_reason}): {api_key[:20]}...")
                        return JSONResponse(
                            status_code=status.HTTP_403_FORBIDDEN,
                            content={
                                "type": "error",
                                "error": {
                                    "type": "permission_error",
                                    "message": f"API key has been deactivated. Reason: {deactivated_reason}. Please contact the administrator.",
                                },
                            },
                        )
                    else:
                        # Deactivated but no reason specified
                        print(f"[AUTH] API key deactivated (no reason): {api_key[:20]}...")
                        return JSONResponse(
                            status_code=status.HTTP_403_FORBIDDEN,
                            content={
                                "type": "error",
                                "error": {
                                    "type": "permission_error",
                                    "message": "API key has been deactivated. Please contact the administrator.",
                                },
                            },
                        )
            except ClientError as e:
                print(f"[AUTH] Error checking deactivation reason: {e}")

            # Key doesn't exist or other error
            print(f"[AUTH] Invalid API key: {api_key[:20]}...")
            return JSONResponse(
                status_code=status.HTTP_401_UNAUTHORIZED,
                content={
                    "type": "error",
                    "error": {
                        "type": "authentication_error",
                        "message": "Invalid API key",
                    },
                },
            )

        # Attach API key info to request state
        request.state.api_key_info = api_key_info

        # Process request
        response = await call_next(request)

        return response


async def get_api_key_info(request: Request) -> dict:
    """
    Dependency to extract API key info from request state.

    Args:
        request: HTTP request

    Returns:
        API key information dictionary

    Raises:
        HTTPException: If not authenticated
    """
    if not hasattr(request.state, "api_key_info"):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                "type": "authentication_error",
                "message": "Not authenticated",
            },
        )

    return request.state.api_key_info
