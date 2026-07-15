FROM python:3.12-slim

WORKDIR /srv/uniforms

# Závislosti
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Balíček a konfigurace nasazení
COPY uniforms/ uniforms/
COPY uniforms.yaml .

# Adresář pro runtime data (SQLite, záznamy, šablony, kolekce)
RUN mkdir -p data

EXPOSE 8000

CMD ["uvicorn", "uniforms.main:app", "--host", "0.0.0.0", "--port", "8000"]
