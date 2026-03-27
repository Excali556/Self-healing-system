FROM python:3.10

RUN apt-get update && apt-get install -y docker.io

WORKDIR /recovery

COPY . .

CMD ["python", "healer.py"]