FROM python:3.12-slim

WORKDIR /app

# Závislosti
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Zdrojový kód
COPY app/ app/
COPY playbooks/ playbooks/

# Adresáře pro runtime data
RUN mkdir -p data

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
