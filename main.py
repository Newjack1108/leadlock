# This file helps Railway detect Python
# Actual application is in api/app/main.py
import sys
import os

# Change to api directory and run the actual app
os.chdir('api')
sys.path.insert(0, os.getcwd())

from app.main import app

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", 8000)))
