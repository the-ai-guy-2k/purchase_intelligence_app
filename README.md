# Purchase Intelligence App

Local web application for understanding purchases over time.

ACI-001 preserves the original receipt image as evidence.

ACI-002 reads that preserved evidence and stores an unconfirmed extraction candidate. The candidate can include a merchant, date, time, totals, and line items. Raw recognized text is kept beside any normalized text. Nothing here confirms a purchase, classifies items, or changes the original image.

Extraction uses the Windows OCR engine already on this machine, behind a replaceable boundary. No paid OCR service is used.

Requesting extraction again for the same evidence ID replaces the previous unconfirmed extraction and its line candidates. One current extraction is kept for each evidence ID. The original receipt file and evidence record are not modified.

## Run

Requires Python 3.12.

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Open http://127.0.0.1:8000

Receipt evidence is written under `data/receipt_evidence/`. Extraction candidates are written under `data/receipt_extraction/`. Both directories are gitignored. Do not commit uploaded receipts or extraction output.

The default text recognizer requires Windows.

## Checks

```powershell
pip install -r requirements-dev.txt
pytest
```
