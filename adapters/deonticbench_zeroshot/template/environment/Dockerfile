FROM ghcr.io/laude-institute/t-bench/python-3-13:20250620

WORKDIR /app

RUN apt-get update && apt-get install -y \
    swi-prolog \
    curl \
    && rm -rf /var/lib/apt/lists/*

RUN curl -fsSL https://claude.ai/install.sh | bash
ENV PATH="/root/.local/bin:$PATH"

RUN mkdir -p /app/output

COPY statute.txt /app/statute.txt
