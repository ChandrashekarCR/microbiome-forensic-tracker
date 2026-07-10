FROM ubuntu:24.04

ENV DEBIAN_FRONTEND=noninteractive

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
    rsync \
    && rm -rf /var/lib/apt/lists/*

RUN curl -sL https://aka.ms/InstallAzureCLIDeb | bash

WORKDIR /app

# Copy the necessary parts
COPY Makefile /app/Makefile
COPY pyproject.toml /app/pyproject.toml
COPY src/ /app/src/
COPY config/ /app/config/
COPY scripts /app/scripts
COPY workflow/ /app/workflow/
COPY profiles/ /app/profiles/
COPY .env.azure /app/.env.azure

ENV ENV_FILE=.env.azure

# Install python enviroment
RUN make venv-all

# Make the venv’s bin directory the default PATH
ENV PATH="/app/.venv-all/bin:${PATH}"

CMD [ "bash" ]

