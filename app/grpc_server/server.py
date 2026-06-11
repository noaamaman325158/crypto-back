import asyncio

import grpc
from grpc_reflection.v1alpha import reflection

from app.core.logging import get_logger
from app.grpc_generated.crypto.insight.v1 import insight_pb2, insight_pb2_grpc
from app.grpc_server.insight_servicer import InsightServicer

logger = get_logger(__name__)

GRPC_PORT = 50051


async def serve() -> None:
    """
    Run the gRPC server alongside FastAPI.
    Called from app/main.py lifespan — both servers share the same process.

    Ports:
      :8000  REST  (FastAPI / uvicorn)
      :50051 gRPC  (this server)

    Server reflection is enabled so grpcurl and Postman can introspect
    available methods without a .proto file:
      grpcurl -plaintext localhost:50051 list
      grpcurl -plaintext localhost:50051 crypto.insight.v1.InsightService/GetInsight
    """
    server = grpc.aio.server()

    insight_pb2_grpc.add_InsightServiceServicer_to_server(InsightServicer(), server)

    # Enable gRPC server reflection — mirrors Dataminr's introspect.go pattern.
    # Allows runtime discovery without recompilation (grpcurl, Postman gRPC, etc.)
    service_names = (
        insight_pb2.DESCRIPTOR.services_by_name["InsightService"].full_name,
        reflection.SERVICE_NAME,
    )
    reflection.enable_server_reflection(service_names, server)

    server.add_insecure_port(f"[::]:{GRPC_PORT}")
    await server.start()
    logger.info("grpc_server_started", port=GRPC_PORT)

    try:
        await server.wait_for_termination()
    except asyncio.CancelledError:
        await server.stop(grace=5)
        logger.info("grpc_server_stopped")
