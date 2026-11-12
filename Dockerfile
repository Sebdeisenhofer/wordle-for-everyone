# Wordle for Everyone: the browser game plus its Python game engine.
# No Rasa or language model needed. Hosts set $PORT; server.py listens on it.
FROM python:3.12-slim
WORKDIR /app
COPY server.py english.py ./
COPY actions/__init__.py actions/wordle_engine.py actions/answers.txt ./actions/
COPY web ./web
ENV PYTHONUNBUFFERED=1
EXPOSE 8001
CMD ["python", "server.py"]
