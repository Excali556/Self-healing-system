FROM python:3.10-slim
RUN pip install docker
WORKDIR /chaos
COPY . .
CMD ["python", "chaos_monkey.py"]