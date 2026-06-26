FROM python:3.11-slim

WORKDIR /code

# LibreDWG (dwg2dxf) untuk konversi file DWG dari customer
RUN apt-get update && apt-get install -y --no-install-recommends \
    libredwg-tools \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "7860"]
