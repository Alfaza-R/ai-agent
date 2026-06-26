FROM python:3.11-slim

WORKDIR /code

# LibreDWG (dwg2dxf) untuk konversi file DWG — build dari source (tarball rilis)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential pkg-config wget ca-certificates xz-utils libpcre2-dev \
    && wget -q https://github.com/LibreDWG/libredwg/releases/download/0.13.4/libredwg-0.13.4.tar.xz -O /tmp/libredwg.tar.xz \
    && cd /tmp && tar xf libredwg.tar.xz && cd libredwg-0.13.4 \
    && ./configure --disable-bindings --disable-shared --disable-dependency-tracking \
    && make -j"$(nproc)" && make install && ldconfig \
    && cd / && rm -rf /tmp/libredwg* \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "7860"]
