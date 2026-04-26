from fastapi import FastAPI

app = FastAPI(
    title="NetOps API",
    description="Network topology discovery and monitoring",
    version="0.1.0"
)


@app.get("/health")
def health_check():
    return {"status": "ok"}


@app.get("/topology")
def get_topology():
    # Placeholder - will be implemented in Phase 1
    return {"nodes": [], "links": []}
