"""Entry point for running as a module."""
from ai_year_wise_dj.api import app
import uvicorn
import os

if __name__ == "__main__":
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)