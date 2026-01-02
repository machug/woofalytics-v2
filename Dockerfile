# Woofalytics Dockerfile
# Multi-stage build for minimal image size

# =============================================================================
# Build Stage
# =============================================================================
FROM python:3.11-slim-bookworm AS builder

WORKDIR /build

# Install build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Install Python build tools
RUN pip install --no-cache-dir build hatchling

# Copy project files
COPY pyproject.toml README.md ./
COPY src ./src

# Build wheel
RUN python -m build --wheel

# =============================================================================
# Runtime Stage
# =============================================================================
FROM python:3.11-slim-bookworm AS runtime

# Labels
LABEL org.opencontainers.image.title="Woofalytics"
LABEL org.opencontainers.image.description="AI-powered dog bark detection with evidence collection"
LABEL org.opencontainers.image.version="2.0.0"

# Install runtime dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    # Audio libraries
    libportaudio2 \
    libasound2 \
    libasound2-plugins \
    alsa-utils \
    # Useful utilities
    curl \
    && rm -rf /var/lib/apt/lists/*

# Create non-root user
RUN useradd --create-home --shell /bin/bash --uid 1000 woofalytics \
    && usermod -aG audio woofalytics

# Set working directory
WORKDIR /home/woofalytics/app

# Copy wheel from build stage
COPY --from=builder /build/dist/*.whl ./

# Install the package
RUN pip install --no-cache-dir *.whl \
    && rm *.whl

# Copy static files and models
COPY --chown=woofalytics:woofalytics static ./static
COPY --chown=woofalytics:woofalytics models ./models

# Create evidence directory
RUN mkdir -p ./evidence && chown woofalytics:woofalytics ./evidence

# Switch to non-root user
USER woofalytics

# Expose port
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8000/api/health || exit 1

# Volume for evidence persistence
VOLUME ["/home/woofalytics/app/evidence"]

# Default command
CMD ["python", "-m", "woofalytics"]
