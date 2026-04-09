FROM python:3.11-slim-bookworm

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Install Playwright browsers and their OS dependencies
RUN playwright install --with-deps chromium

COPY src/ src/

VOLUME /app/output

ENTRYPOINT ["python", "src/main.py"]
