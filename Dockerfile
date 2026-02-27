FROM python:3.12-slim
WORKDIR /app
RUN pip install --no-cache-dir python-telegram-bot[ext] httpx
COPY bot.py .
CMD ["python", "bot.py"]
