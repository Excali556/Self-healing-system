from fastapi import FastAPI
import random

app = FastAPI()

@app.get("/")
def home():
    return {"message": "Service running"}

@app.get("/health")
def health():
    # simulate random failure
    if random.randint(1, 10) > 8:
        raise Exception("Random failure")
    return {"status": "healthy"}