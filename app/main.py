"""FastAPI-застосунок. Вебхуки каналів підключаються на етапах 3 і 5."""

from fastapi import FastAPI

app = FastAPI(title="MDs manager")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
