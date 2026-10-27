# ---------------------------------------------------------------------------
# Build stage — resolve the dependencies into a self-contained virtualenv.
# The compiler toolchain lives here and never reaches the final image.
#
# Both stages must share the same base image: the virtualenv's interpreter is a
# symlink to /usr/local/bin/python3.11, which has to exist at the same path in
# the runtime stage.
# ---------------------------------------------------------------------------
FROM python:3.11-slim AS builder

# Today's dependencies are all pure Python and install from wheels, but a
# transitive one may need building on arm64. The toolchain is free here, since
# this stage is discarded.
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        gcc \
        python3-dev \
        libssl-dev \
        build-essential && \
    rm -rf /var/lib/apt/lists/*

RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Only requirements.txt is copied, so editing the app does not invalidate this
# layer and rebuild every dependency.
COPY app/requirements.txt .
RUN pip install --no-cache-dir --upgrade pip setuptools wheel && \
    pip install --no-cache-dir -r requirements.txt


# ---------------------------------------------------------------------------
# Runtime stage — the virtualenv, the app, and nothing else to build with.
# ---------------------------------------------------------------------------
FROM python:3.11-slim

# curl serves the container healthcheck in docker-compose.yml. It is the only
# package the runtime image adds.
RUN apt-get update && \
    apt-get install -y --no-install-recommends curl && \
    rm -rf /var/lib/apt/lists/*

COPY --from=builder /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

WORKDIR /app

COPY app/app.py .
COPY app/templates ./templates/
COPY static ./static/

ENV FLASK_APP=app.py
ENV PYTHONUNBUFFERED=1

EXPOSE 5000

# A single worker, with threads for concurrency: sessions are held in the
# process's memory, so a second worker would not see them and every other
# request would bounce the user back to the login page. The work is all
# waiting on the CardDAV server, so threads cover it.
CMD ["gunicorn", "--bind", "0.0.0.0:5000", "--workers", "1", "--threads", "8", "--timeout", "60", "app:app"]
