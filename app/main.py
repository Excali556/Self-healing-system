from fastapi import FastAPI
import random

app = FastAPI()

@app.get("/")
def home():
    return {"message": "Service running"}

@app.get("/health")
def health():
    return {"status": "healthy"}