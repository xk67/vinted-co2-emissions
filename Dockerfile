FROM python:3.13-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    HOST=0.0.0.0 \
    PORT=5000

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Bake the German cities dataset into the image so it does not need to be
# downloaded at runtime. The dummy cookie only satisfies the config loader.
RUN VINTED_COOKIE=build-only python3 cities.py

EXPOSE 5000

# Provide the Vinted cookie at runtime, e.g.
#   docker run -p 5000:5000 -e VINTED_COOKIE="access_token_web=..." vinted-co2
CMD ["python3", "app.py"]
