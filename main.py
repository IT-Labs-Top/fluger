from fastapi import FastAPI

app = FastAPI(title="Fluger API")


@app.get("/")
def root():
    return {"status": "ok"}


@app.get("/health")
def health():
    return {"healthy": True}
