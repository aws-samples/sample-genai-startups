import subprocess

subprocess.run([
    "gunicorn", "app:app", 
    "--bind", "127.0.0.1:5000",
    "--workers", "2", 
    "--preload", 
    "-k", "uvicorn.workers.UvicornWorker"
])
