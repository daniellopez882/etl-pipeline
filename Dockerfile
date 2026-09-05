# The previous image was python:3.8 (end of life), ran as root, and copied
# the whole tree. Multi-stage on 3.12-slim, uid 10001, application files only.
FROM python:3.12-slim AS build

WORKDIR /app
ENV PIP_NO_CACHE_DIR=1 PIP_DISABLE_PIP_VERSION_CHECK=1

COPY requirements.txt .
RUN python -m venv /opt/venv \
 && /opt/venv/bin/pip install --upgrade pip \
 && /opt/venv/bin/pip install -r requirements.txt


FROM python:3.12-slim AS runtime

RUN useradd --create-home --uid 10001 etl

WORKDIR /app
COPY --from=build /opt/venv /opt/venv
COPY --chown=etl:etl main.py ./
COPY --chown=etl:etl src/ ./src/

RUN mkdir -p /app/out && chown etl:etl /app/out
VOLUME ["/app/out"]

ENV PATH="/opt/venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

USER etl

# A one-shot job: the exit code is the result. --dry-run writes to /app/out.
ENTRYPOINT ["python", "main.py"]
