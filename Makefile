.PHONY: proto lint test run

SITE := $(shell python3 -c "import site; print(site.getsitepackages()[0])")

# Regenerate gRPC Python stubs from .proto files.
# Run this after any change to proto/
proto:
	python3 -m grpc_tools.protoc \
		-I proto \
		-I "$(SITE)" \
		--python_out=app/grpc_generated \
		--grpc_python_out=app/grpc_generated \
		proto/crypto/insight/v1/insight.proto
	@# Fix the generated import path to be absolute from the project root
	@sed -i '' 's|from crypto.insight.v1 import insight_pb2|from app.grpc_generated.crypto.insight.v1 import insight_pb2|g' \
		app/grpc_generated/crypto/insight/v1/insight_pb2_grpc.py
	@echo "✓ Stubs regenerated"

lint:
	ruff check .

test-unit:
	pytest tests/unit/ -v

test-integration:
	pytest tests/integration/ -v

run:
	uvicorn app.main:app --reload --port 8000
