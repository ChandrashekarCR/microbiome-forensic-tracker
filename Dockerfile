FROM ubuntu:24.04

ENV DEBIAN_FRONTENF=noninteractive

# Install system dependencies
RUN apt-get update && \
    apt-get install -y \
    python3 \
    python3-pip \
    python3-venv \
    python-is-python3 \
    git \
    make \
    wget \
    curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy the necessary parts
COPY Makefile /app/Makefile
COPY pyproject.toml /app/pyproject.toml
COPY src/ /app/src/
COPY config/ /app/config/
COPY workflow/ /app/workflow/
COPY profiles/ /app/profiles/

ENV ENV_FILE=.env.local

# Install python enviroment
RUN make venv-all

# Make the venv’s bin directory the default PATH
ENV PATH="/app/.venv-all/bin:${PATH}"

EXPOSE 8000

# Run the fastapi backend
# To run Celery worker instead, override CMD: docker run ... celery -A src.backend.celery_app worker --loglevel=info
CMD ["uvicorn", "src.backend.main:app", "--host", "0.0.0.0", "--port", "8000"]