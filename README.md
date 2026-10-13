# Federated Learning FLamby EHR

Research prototype for simulated EHR task evaluation and selected federated-learning utilities. The source includes a local FastAPI operations console, command-line tools, numerical aggregators, non-IID dataset partitioners, and experimental secret-sharing helpers.

**Scope:** This is not a complete FLamby integration or a working cross-hospital federated training system. It does not train models on FLamby datasets, coordinate actual hospital nodes, provide end-to-end secure aggregation, or implement production-grade differential privacy, homomorphic encryption, or clinical validation.

## Available functionality

- **Local evaluation service:** three deterministic workers review synthetic task metrics and emit an urgency dossier. Exposes `GET /`, `GET /health`, `GET /metrics`, `POST /api/audit`, `POST /api/chat`, and `GET /api/audit/logs`.
- **CLI and CSV batch mode:** evaluate example records, export results, inspect the current in-process audit chain, and run a synthetic workload.
- **Federated numerical utilities:** weighted FedAvg, Krum, Multi-Krum, coordinate-wise trimmed mean, cosine-based anomaly screening, and Dirichlet/label-skew dataset partitioners (NumPy).
- **Experimental dropout utilities:** Shamir reconstruction with Feldman share commitments and per-round dropout tracking. The included 61-bit share field and 67-bit commitment group are **not sized for production cryptographic security**.
- **In-memory HMAC-SHA256 audit chain:** verifies individual entry signatures and chain linkage; records are lost when the process exits.
- **Operations console:** a responsive local HTML page that requires the Python API. If the server is unavailable, it reports an error rather than manufacturing results.

The “chat” provider factory currently returns a deterministic mock for every provider setting, including settings named after external providers. No external model API calls are implemented.

## Local installation

Requires Python 3.9+ and a strong random audit key.

```bash
git clone https://github.com/abusuraihsakhri/federated-learning-flamby-ehr.git
cd federated-learning-flamby-ehr
python -m venv .venv
source .venv/bin/activate           # Windows: .venv\Scripts\activate
python -m pip install -e .
export AUDIT_SECRET_KEY="$(python -c 'import secrets; print(secrets.token_hex(32))')"
python cli.py serve --host 127.0.0.1 --port 8000
```

Open [the local operations console](http://127.0.0.1:8000/) in your browser. The API documentation is at `/docs`. In Windows PowerShell, set the environment variable with `$env:AUDIT_SECRET_KEY = "<random-key>"` instead of `export`.

Example commands (with `AUDIT_SECRET_KEY` set):

```bash
python cli.py audit --task-id DEMO-001 --target SYNTHETIC-001 --primary 28.5 --secondary 14.2 --critical --status DISCORDANT
python cli.py batch -i sample.csv -o results.csv
python cli.py verify-audit
python simulator.py --tasks 100 --seed 42
```

For the legacy `federated_learning_ehr` CLI, use `python federated_learning_ehr_app.py --help`. Its demonstration evaluation path is separate from the main `agents` API.

## Docker

```bash
cp .env.example .env
# Replace AUDIT_SECRET_KEY= with a randomly generated secret (at least 16 characters).
docker compose up --build
```

The Compose configuration binds port 8000 to localhost, not every network interface. The Python API must run on a server; GitHub Pages cannot host the full service or safely retain its secret signing key. **No live GitHub Pages application is claimed or linked.**

## Testing

```bash
python -m pip install -e ".[test]"
export AUDIT_SECRET_KEY="test-audit-secret-key-for-pytest-suite-2026"
pytest -v
```

GitHub Actions tests Python 3.10, 3.11, and 3.12, checks syntax, and builds a distributable wheel. Browser JavaScript is syntax-checked when Node.js is available.

## Privacy, security, and limitations

**Use synthetic data only. Do not enter patient identifiers, clinical records, secrets, or other protected health information.** The project has no user authentication, authorization, TLS termination, encrypted database, or durable audit-log storage. Its regex-based identifier guard catches selected patterns but **cannot establish HIPAA Safe Harbor de-identification or GDPR compliance**. The local browser console sends inputs to the running FastAPI server; it does not process EHR records entirely in the browser. Numerical aggregation, experimental VSS, and simulated scoring must not be interpreted as deployed secure aggregation or clinical decision support.

The dependency-free `enrichment.py` module provides threshold-based illustrative checks; its named features do not implement the named production algorithms. Actual FLamby dataset loading, training rounds, and independently validated privacy guarantees remain future work.

## Repository layout

- `agents/` — synthetic evaluation workers, HMAC ledger, API, and mock model provider
- `federated_learning_ehr/` — numerical aggregation, partitioning, experimental VSS, and legacy CLI
- `web/` — operations console, packaged with the Python distribution
- `cli.py` and `simulator.py` — main CLI and synthetic workload
- `tests/` — unit, integration, and regression tests
- `.github/workflows/ci.yml` — CI on pull requests and master/main pushes

## License

MIT — see [LICENSE](LICENSE).
