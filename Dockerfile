# syntax=docker/dockerfile:1.7
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONFAULTHANDLER=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

ARG TORCH_VERSION=2.8.0

# git is required for requirements that install from GitHub. The libs are for
# opencv-python (pulled in by ultralytics for chart extraction), which links
# against X11/GL even when nothing is displayed; without them `import cv2` fails.
# tesseract-ocr is the system binary pytesseract shells out to for
# screenshot OCR (app/ml/image_text.py, issue #88; opt-in via
# IMAGE_OCR_ENABLED, but the binary needs to be present either way).
RUN --mount=type=cache,target=/var/cache/apt,sharing=locked \
    --mount=type=cache,target=/var/lib/apt,sharing=locked \
    apt-get update \
    && apt-get install -y --no-install-recommends git libgl1 libglib2.0-0 libxcb1 tesseract-ocr \
    && rm -rf /var/lib/apt/lists/*

RUN --mount=type=cache,target=/root/.cache/pip,sharing=locked \
    pip install --upgrade pip setuptools wheel \
    && pip install \
         --index-url https://download.pytorch.org/whl/cpu \
         --extra-index-url https://pypi.org/simple \
         "torch==${TORCH_VERSION}" torchvision

# torchvision comes from the CPU index above and is pinned here too: left to
# PyPI (ultralytics/timm pull it in), it is a build whose compiled ops don't
# load against CPU torch ("operator torchvision::nms does not exist"), which
# breaks every transformers pipeline import, sentiment included.
COPY requirements.txt ./
RUN --mount=type=cache,target=/root/.cache/pip,sharing=locked \
    grep -Ev '^torch([[:space:]]|$|[<>=!~])' requirements.txt > requirements.no-torch.txt \
    && pip freeze | grep -E '^(torch|torchvision)==' > constraints.txt \
    && pip install -c constraints.txt -r requirements.no-torch.txt \
    && rm -f requirements.no-torch.txt constraints.txt

# Fail fast during image build if PyTorch CPU execution is not compatible.
RUN TORCH_VERSION_EXPECTED="${TORCH_VERSION}" python - <<'PY'
import platform
import torch
import os

import cv2  # noqa: F401  (fails here, not at runtime, if its system libs are missing)
import torchvision

x = torch.randn(8, 8)
_ = x @ x
# Exercises torchvision's compiled ops, which a torch/torchvision build
# mismatch breaks while plain torch still works.
boxes = torch.tensor([[0.0, 0.0, 1.0, 1.0], [0.1, 0.1, 1.1, 1.1]])
_ = torchvision.ops.nms(boxes, torch.tensor([0.9, 0.8]), 0.5)
print("torch_ok", platform.machine(), torch.__version__, torchvision.__version__)

expected = os.environ.get("TORCH_VERSION_EXPECTED", "").strip()
actual = torch.__version__.split("+", 1)[0]
if expected and actual != expected:
    raise RuntimeError(f"Unexpected torch version: expected {expected}, got {torch.__version__}")
PY

COPY app ./app

EXPOSE 7999

CMD ["uvicorn", "app.api.main:app", "--host", "0.0.0.0", "--port", "7999", "--log-config", "app/logging.ini"]
