FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

# RAR support: Debian's packaged 7zip is built without the unRAR code, so install RARLAB's `unrar` from non-free.
RUN sed -i 's/^Components: main.*/Components: main non-free/' /etc/apt/sources.list.d/debian.sources \
    && apt-get update \
    && apt-get install -y --no-install-recommends unrar \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY medialink /app/medialink

# Runs as the media owner (compose sets user: 1000:1000) so links and directories keep the library's ownership.
ENTRYPOINT ["python", "-m", "medialink"]
CMD ["run"]
