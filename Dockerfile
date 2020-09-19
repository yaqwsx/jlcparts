FROM ubuntu:20.04

RUN env DEBIAN_FRONTEND=noninteractive \
    apt-get update && \
    apt-get install -y --no-install-recommends \
        python3 python3-pip nodejs npm wget zip unzip libreoffice && \
    pip3 install requests click && \
    rm -rf /var/lib/apt/lists/*