FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# git is required for requirements that install from GitHub.
RUN apt-get update \
    && apt-get install -y --no-install-recommends git \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt ./
RUN pip install --upgrade pip \
    && pip install --index-url https://download.pytorch.org/whl/cpu torch \
    && grep -Ev '^torch([[:space:]]|$|[<>=!~])' requirements.txt > requirements.no-torch.txt \
    && pip install -r requirements.no-torch.txt \
    && rm -f requirements.no-torch.txt

COPY app ./app
COPY curl.txt ./curl.txt

EXPOSE 8000

CMD ["uvicorn", "app.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
