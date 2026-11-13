# Agentic Universe – Interaction Ledger & Reporting Pipeline

A Python-based data ingestion and reporting pipeline designed to process interaction events, handle inconsistent input data, maintain a reliable interaction ledger, and generate accurate reports.

## Overview

This project implements **Assignment A: Interaction Ledger & Reporting Pipeline** for the Agentic Universe Junior SDE Take-Home Challenge.

The system focuses on reliable ingestion of interaction data, structured database storage, data normalization, validation, and reporting.

It is designed to handle messy input data while maintaining data consistency, preventing duplicate processing, and ensuring that interaction records remain traceable.

## Key Features

- **Data Ingestion:** Processes incoming interaction data and handles different input formats.
- **Data Normalization:** Standardizes inconsistent input values before database insertion.
- **Data Validation:** Handles invalid, incomplete, and malformed records.
- **Interaction Ledger:** Maintains structured interaction records for reliable tracking and reporting.
- **Idempotent Processing:** Supports safe repeated processing without creating duplicate records.
- **Database Management:** Uses SQLite for persistent storage and structured data management.
- **PII Protection:** Implements encryption mechanisms to protect sensitive information.
- **Reporting Pipeline:** Generates reports from structured interaction data.
- **Error Handling:** Handles ingestion failures and rejected records systematically.
- **Automated Testing:** Includes tests covering core processing and data-handling functionality.

## Technology Stack

| Component | Technology |
|---|---|
| Language | Python 3.11+ |
| Database | SQLite |
| Testing | pytest |
| Data Processing | Python |
| Security | PII Encryption |

## Project Structure

```text
agentic-universe-sde-assignment/
│
├── assignment-a-data/
│   └── Original assignment specification
│
├── assignment-b-workflow/
│   └── Original assignment specification
│
├── solution/
│   ├── README.md
│   ├── ingestion.py
│   ├── events.py
│   ├── database.py
│   ├── reporting.py
│   └── normalizers.py
│
├── tests/
│   └── Automated test cases
│
├── docs/
│   └── Supporting documentation
│
├── requirements.txt
├── SUBMISSION.md
├── AI_USAGE.md
└── README.md
```

## Getting Started

### Prerequisites

- Python 3.11 or later
- Git

### 1. Clone the repository

```bash
git clone <YOUR_PRIVATE_REPOSITORY_URL>
cd agentic-universe-sde-assignment
```

### 2. Create a virtual environment

**Windows PowerShell:**

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
```

**Linux / macOS:**

```bash
python3 -m venv .venv
source .venv/bin/activate
```

### 3. Install dependencies

```bash
pip install -r requirements.txt
```

### 4. Run tests

```bash
pytest -v
```

## Architecture

The implementation is organized into separate modules to maintain clear responsibilities.

| Module | Responsibility |
|---|---|
| `ingestion.py` | Handles incoming data ingestion and processing |
| `events.py` | Handles interaction event operations |
| `database.py` | Manages database operations and persistence |
| `normalizers.py` | Normalizes incoming data |
| `reporting.py` | Handles reporting and metric generation |

This modular structure separates ingestion, processing, persistence, and reporting logic, making the system easier to maintain and extend.

## Testing

The project includes automated tests for core functionality, including:

- Data ingestion and processing
- Input normalization
- Database operations
- Interaction event handling
- Reporting functionality
- Error handling and edge cases

Run the complete test suite:

```bash
pytest -v
```

**Latest recorded test result: 45 tests passed.**

## Design Considerations

The implementation prioritizes:

1. **Correctness:** Consistent processing and accurate reporting.
2. **Reliability:** Safe handling of repeated operations and invalid inputs.
3. **Data Integrity:** Structured persistence and validation.
4. **Security:** Protection of sensitive information.
5. **Maintainability:** Modular code organization and separation of responsibilities.

## Scope and Limitations

This implementation focuses on the data layer of the Agentic Universe platform.

The durable campaign dispatcher described in Assignment B is not part of this submission.

Further improvements could include expanded reporting capabilities, additional database optimization, and broader failure-recovery testing.

## Submission

This repository contains the implementation for Assignment A of the Agentic Universe Junior SDE Take-Home Challenge.

- Assignment: Interaction Ledger & Reporting Pipeline
- Language: Python
- Database: SQLite
- Tests: pytest
- Documentation: `SUBMISSION.md` and `AI_USAGE.md`

