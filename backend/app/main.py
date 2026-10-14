from fastapi import FastAPI


app = FastAPI(title="Yab's Salon Management System API")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
