FROM python:3.10-slim

WORKDIR /app

# Dependencias
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copiamos la app Flask (código + templates)
COPY Food_delivery/Deploying_Predictive_Systems/web/ /app/

# Ajustes
ENV PYTHONUNBUFFERED=1
EXPOSE 5050
CMD ["python", "MY_flask_api.py"]