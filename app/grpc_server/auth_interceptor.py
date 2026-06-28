"""
gRPC server-side JWT authentication interceptor.

The REST insight endpoint is protected by `get_current_user` (a Bearer JWT).
The gRPC transport exposes the same Claude-backed logic, so it must enforce the
same authentication — otherwise anyone who can reach :50051 could trigger paid
Anthropic calls. This interceptor validates the same access token REST issues,
reusing `decode_token` so both transports share one source of truth.

Clients send the token as gRPC metadata:
    authorization: Bearer <access_token>

Reflection calls are allowed through unauthenticated so tooling (grpcurl,
Postman) can still introspect the service; only RPC methods require a valid JWT.
"""

import grpc

from app.core.logging import get_logger
from app.core.security import decode_token

logger = get_logger(__name__)

# Reflection service methods are allowed without auth so clients can still
# discover the API surface. Everything else requires a valid access token.
_PUBLIC_METHOD_PREFIXES = ("/grpc.reflection.",)


def _is_public(method: str) -> bool:
    return method.startswith(_PUBLIC_METHOD_PREFIXES)


class JWTAuthInterceptor(grpc.aio.ServerInterceptor):
    """Rejects RPCs that don't carry a valid Bearer access token in metadata."""

    async def intercept_service(self, continuation, handler_call_details):
        method = handler_call_details.method
        if _is_public(method):
            return await continuation(handler_call_details)

        metadata = dict(handler_call_details.invocation_metadata or ())
        auth_header = metadata.get("authorization", "")

        token = _extract_bearer(auth_header)
        if token is None:
            return _abort_handler(
                grpc.StatusCode.UNAUTHENTICATED,
                "Missing or malformed Authorization metadata (expected 'Bearer <token>')",
            )

        try:
            payload = decode_token(token)
        except Exception:
            logger.warning("grpc_auth_invalid_token", method=method)
            return _abort_handler(grpc.StatusCode.UNAUTHENTICATED, "Invalid or expired token")

        if payload.get("type") != "access":
            return _abort_handler(grpc.StatusCode.UNAUTHENTICATED, "Invalid token type")

        return await continuation(handler_call_details)


def _extract_bearer(auth_header: str) -> str | None:
    parts = auth_header.split()
    if len(parts) == 2 and parts[0].lower() == "bearer":
        return parts[1]
    return None


def _abort_handler(code: grpc.StatusCode, detail: str) -> grpc.RpcMethodHandler:
    """Return a handler that aborts every call with the given status."""

    async def abort(request, context: grpc.aio.ServicerContext):
        await context.abort(code, detail)

    return grpc.unary_unary_rpc_method_handler(abort)
