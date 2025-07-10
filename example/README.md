# Example UTCP

## Build
0. Install utcp (go at the end of [UTCP README](../README.md))
1. Enable environment (e.g. `conda activate utcp`)
2. Install required libraries (`pip install -r requirements.txt`)
3. Run server on port 8080: `uvicorn server:app --host 0.0.0.0 --port 8080`
4. Run client to fetch manual and run the first defined tool: `python client.py`

