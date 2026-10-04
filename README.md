# Purchase Intelligence App

Local web application for understanding purchases over time.

ACI-001 preserves the original receipt image as evidence.

ACI-002 reads that preserved evidence and stores an unconfirmed extraction candidate. The candidate can include a merchant, date, time, totals, and line items. Raw recognized text is kept beside any normalized text. Nothing here confirms a purchase, classifies items, or changes the original image.

Extraction uses the Windows OCR engine already on this machine, behind a replaceable boundary. No paid OCR service is used.

Requesting extraction again for the same evidence ID replaces the previous unconfirmed extraction and its line candidates. One current extraction is kept for each evidence ID. The original receipt file and evidence record are not modified.

ACI-003 adds review, correction, and explicit confirmation. Confidence is a deterministic review hint: high for an unambiguous parsed value, medium for a text candidate, low when a value is missing or the raw text shows something the parser refused, and absent when an optional value was not on the receipt. Highlighted fields can be corrected. Blank optional fields stay null.

Confirm purchase is the only action that creates a confirmed purchase. One extraction has one confirmed purchase. Confirming that extraction again is rejected, and the confirmed record is read-only. The raw extraction text and the original receipt are not rewritten. Each confirmed item keeps the source line id and the raw line text.

ACI-004 remembers a confirmed purchase. Purchase history is created only from that confirmed record, one memory record per purchase. Remembering the same purchase again reuses the existing record and does not change classifications. The confirmed purchase and the original receipt stay unchanged.

Classification is conservative and local. Obvious item words can be marked food or non-food, and consumable or long-term. Need versus want stays unknown until you set it. An unrecognized item stays unknown. You can correct any of the three labels. Purchase history shows what was purchased. It does not claim those items are still in the household.

ACI-005 calculates purchase patterns from purchase history when the patterns page is opened. Nothing is stored as a second copy of the purchases. Item comparison trims surrounding space, collapses inner space, and casefolds the name. Different words stay different items. A repeat is the same comparison key on more than one remembered purchase. An interval is calculated only when at least two of those purchases have dates. Missing quantities and dates stay missing. Changing a classification changes the next count. Opening the patterns page does not change purchase history.

## Run

Requires Python 3.12.

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Open http://127.0.0.1:8000

Receipt evidence is written under `data/receipt_evidence/`. Extraction candidates are written under `data/receipt_extraction/`. Confirmed purchases are written under `data/confirmed_purchases/`. Purchase history is written under `data/purchase_memory/`. Those directories are gitignored. Do not commit uploaded receipts, extractions, confirmed purchases, or purchase history.

The default text recognizer requires Windows.

## Checks

```powershell
pip install -r requirements-dev.txt
pytest
```
