# N16 - reproducible runtime for the lab's llama-server (CPU build, same pinned release
# as lib/labkit.py LLAMA_CPP_BUILD). Weights are NOT baked in: they are mounted.
FROM ubuntu:24.04
ARG LLAMA_CPP_BUILD=b10488
RUN apt-get update \
 && apt-get install -y --no-install-recommends ca-certificates curl libgomp1 \
 && rm -rf /var/lib/apt/lists/*
RUN curl -fsSL -o /tmp/llama.tgz \
      "https://github.com/ggml-org/llama.cpp/releases/download/${LLAMA_CPP_BUILD}/llama-${LLAMA_CPP_BUILD}-bin-ubuntu-x64.tar.gz" \
 && mkdir -p /opt/llama && tar -xzf /tmp/llama.tgz -C /opt/llama --strip-components=1 \
 && rm /tmp/llama.tgz
ENV LD_LIBRARY_PATH=/opt/llama
RUN useradd --system --no-create-home llama
USER llama
ENTRYPOINT ["/opt/llama/llama-server"]
