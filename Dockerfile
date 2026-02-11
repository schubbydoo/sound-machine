# ---- Base image ----
FROM python:3.12-slim

# ---- Environment ----
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# ---- System deps ----
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    ca-certificates \
    procps \
    iproute2 \
    && rm -rf /var/lib/apt/lists/*

# ---- Working directory ----
WORKDIR /app

# ---- Copy application code ----
COPY . /app

# ---- Python dependencies ----
RUN python -m venv /venv \
    && /venv/bin/pip install --upgrade pip \
    && /venv/bin/pip install flask gunicorn

# ---- Runtime env ----
ENV PATH="/venv/bin:$PATH"
ENV MSS_ROOT=/app
ENV MSS_DATA_DIR=/app/data
ENV MSS_SOUNDS_DIR=/app/Sounds

# ---- Expose port ----
EXPOSE 8080

# ---- Run web UI only ----
CMD ["gunicorn", "-w", "2", "-b", "0.0.0.0:8080", "web_interface.backend.wsgi:application"]
