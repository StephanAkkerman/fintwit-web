# syntax=docker/dockerfile:1.7
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONFAULTHANDLER=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

ARG TORCH_VERSION=2.8.0

# git is required for requirements that install from GitHub.
# tesseract-ocr is the system binary pytesseract shells out to for
# screenshot OCR (app/ml/image_text.py, issue #88; opt-in via
# IMAGE_OCR_ENABLED, but the binary needs to be present either way).
RUN --mount=type=cache,target=/var/cache/apt,sharing=locked \
    --mount=type=cache,target=/var/lib/apt,sharing=locked \
    apt-get update \
    && apt-get install -y --no-install-recommends git tesseract-ocr \
    && rm -rf /var/lib/apt/lists/*

RUN --mount=type=cache,target=/root/.cache/pip,sharing=locked \
    pip install --upgrade pip setuptools wheel \
    && pip install \
         --index-url https://download.pytorch.org/whl/cpu \
         --extra-index-url https://pypi.org/simple \
         "torch==${TORCH_VERSION}"

COPY requirements.txt ./
RUN --mount=type=cache,target=/root/.cache/pip,sharing=locked \
    grep -Ev '^torch([[:space:]]|$|[<>=!~])' requirements.txt > requirements.no-torch.txt \
    && printf 'torch==%s\n' "${TORCH_VERSION}" > constraints.txt \
    && pip install -c constraints.txt -r requirements.no-torch.txt \
    && rm -f requirements.no-torch.txt constraints.txt

# Fail fast during image build if PyTorch CPU execution is not compatible.
RUN TORCH_VERSION_EXPECTED="${TORCH_VERSION}" python - <<'PY'
import platform
import torch
import os

x = torch.randn(8, 8)
_ = x @ x
print("torch_ok", platform.machine(), torch.__version__)

expected = os.environ.get("TORCH_VERSION_EXPECTED", "").strip()
actual = torch.__version__.split("+", 1)[0]
if expected and actual != expected:
    raise RuntimeError(f"Unexpected torch version: expected {expected}, got {torch.__version__}")
PY

COPY app ./app
COPY curl.txt ./curl.txt

EXPOSE 7999

CMD ["uvicorn", "app.api.main:app", "--host", "0.0.0.0", "--port", "7999", "--log-config", "app/logging.ini"]
