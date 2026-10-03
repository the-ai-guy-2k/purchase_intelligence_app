# Purchase Intelligence App

Local web application for understanding purchases over time.

ACI-001 scope is receipt intake and original evidence preservation only. The uploaded image is stored as evidence. This application does not extract, normalize, classify, or analyze the receipt.

## Run

Requires Python 3.12.

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Open http://127.0.0.1:8000

Receipt evidence is written under `data/receipt_evidence/` on this machine. That directory is gitignored. Do not commit uploaded receipts.

## Checks

```powershell
pip install -r requirements-dev.txt
pytest
```
