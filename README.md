# Federated Learning Flamby Ehr

> **Domain:** Privacy-Preserving Healthcare & Federated Computing
> **Reference Guidelines & Standards:** `HIPAA Safe Harbor §164.514 & Differential Privacy RDP`

<div align="center">

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
![Python](https://img.shields.io/badge/Python-3.10%20%7C%203.11%20%7C%203.12-3776AB.svg?logo=python&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-0.111-009688.svg?logo=fastapi&logoColor=white)
![Audit Trail](https://img.shields.io/badge/Audit-HMAC--SHA256_Tamper--Evident-brightgreen.svg)
![Zero-PHI Guard](https://img.shields.io/badge/Guard-Zero--PHI_Outbound-blue.svg)
![Docker](https://img.shields.io/badge/Docker-Ready-2496ED.svg?logo=docker&logoColor=white)

</div>

---

## 📖 What It Does

**Federated Learning Flamby Ehr** is a federated learning platform implementing Federated Averaging (FedAvg) & Secure Aggregation (SecAgg) for multi-hospital EHR analytics. It provides a multi-worker evaluation system with Byzantine-resilient aggregation, verifiable secret sharing for dropout resilience, and strict PHI (Protected Health Information) outbound guardrails.

---

## ⚙️ Key Capabilities & Algorithmic Modules

- **Multi-Worker Evaluation**: Three specialized workers (InvariantQC, SafetyEscalation, ProtocolConformance) evaluate tasks in parallel
- **Byzantine-Resilient Aggregation**: Krum, Multi-Krum, and Trimmed Mean algorithms to detect and reject poisoned model updates
- **Verifiable Secret Sharing (VSS)**: Feldman VSS for dropout-resilient SecAgg
- **Zero-PHI Outbound Guard**: AST and regex inspection blocking SSNs, MRNs, phone numbers, emails, and patient identifiers
- **HMAC-SHA256 Audit Trail**: Cryptographically chained, tamper-evident logging
- **Cross-Silo Data Partitioning**: Dirichlet, quantity skew, label skew strategies for non-IID hospital data
- **Active Learning Calibration**: Bayesian worker reliability weight tracking
- **FastAPI REST API**: OpenAPI 3.1 endpoints with Prometheus telemetry

---

## 🚀 Quickstart

### Prerequisites
- Python 3.9+
- Set the `AUDIT_SECRET_KEY` environment variable (minimum 16 characters)

```bash
# Clone and setup
git clone https://github.com/abusuraihsakhri/federated-learning-flamby-ehr.git
cd federated-learning-flamby-ehr

# Set required environment variable
export AUDIT_SECRET_KEY="your-secure-key-here"  # Linux/macOS
set AUDIT_SECRET_KEY=your-secure-key-here        # Windows
```

### Install Dependencies
```bash
pip install fastapi uvicorn pydantic pytest
```

### Generate a Secure Audit Key
```bash
python -c "import secrets; print(secrets.token_hex(32))"
```

---

## 💻 CLI Usage

### Single Task Evaluation
```bash
python cli.py audit --task-id TASK-001 --target KEY-01 --primary 28.5 --secondary 14.2 --critical --status DISCORDANT
```

### Batch CSV Processing
```bash
python cli.py batch -i sample.csv -o results.csv
```

### Supervisory Chat
```bash
python cli.py chat "What is the system status?"
```

### Verify Audit Trail
```bash
python cli.py verify-audit
```

### Launch REST API Server
```bash
python cli.py serve --host 127.0.0.1 --port 8000
```

### High-Throughput Simulation
```bash
python simulator.py --tasks 1000 --seed 42
```

---

## 🐳 Docker Deployment

```bash
# Copy and customize environment
cp .env.example .env
# Edit .env with your secure AUDIT_SECRET_KEY

# Build and run
docker compose up --build
# API available at http://localhost:8000
```

---

## 🛡️ Security Architecture

* **Zero-PHI Outbound Interceptor:** Blocks SSNs, MRNs, phone numbers, emails, DOB patterns, and known patient name patterns from any outbound data stream.
* **Tamper-Evident HMAC-SHA256 Audit Trail:** Chained, cryptographically signed logs for every evaluation and state transition. Key must be provided via `AUDIT_SECRET_KEY` environment variable.
* **Byzantine Detection:** Cosine similarity-based anomaly detection flags compromised hospital nodes with configurable trust score decay.
* **Secure Defaults:** No hardcoded secrets; audit key required at startup with minimum 16-character length enforcement.

---

## 🧪 Testing

```bash
# Set test key and run full suite
export AUDIT_SECRET_KEY="test-audit-secret-key-for-pytest-suite-2026"
pytest -v
```

Test coverage includes:
- PHI guard enforcement (SSN, MRN, email blocking)
- Specialized worker alert generation
- Supervisor consensus and audit integrity
- Audit key validation and short-key rejection
- Batch CSV processing with malformed row handling
- Simulator deterministic output with seed control

---

## 📁 Project Structure

```
federated-learning-flamby-ehr/
├── agents/                        # Core evaluation workers and API
│   ├── base.py                    # PHI guard, audit trail, security exceptions
│   ├── supervisor.py              # Multi-worker orchestrator
│   ├── workers.py                 # InvariantQC, SafetyEscalation, ProtocolConformance
│   ├── models.py                  # Pydantic schemas
│   ├── api.py                     # FastAPI endpoints
│   ├── learning.py                # Bayesian calibration engine
│   ├── metrics.py                 # Prometheus exporter
│   └── streamer.py                # WebSocket telemetry
├── federated_learning_ehr/        # Federated learning algorithms
│   ├── byzantine_aggregators.py   # Krum, Multi-Krum, Trimmed Mean
│   ├── dropout_handler.py         # Verifiable Secret Sharing for dropout resilience
│   ├── partitioner.py             # Non-IID data partitioning strategies
│   ├── engine.py                  # Domain evaluation engine
│   └── agents.py                  # Federated coordinator and sub-agents
├── tests/                         # Pytest test suite
├── web/index.html                 # Operations console UI
├── cli.py                         # Main CLI entry point
├── simulator.py                   # High-throughput testing simulator
├── enrichment.py                  # Feature evaluation engines
├── docker-compose.yml             # Container orchestration
└── pyproject.toml                 # Project metadata
```

---

## 📄 License

MIT License - see [LICENSE](LICENSE) for details.
