_Last updated: 20260707_

> **Historical.** Superseded by [architecture.md](../architecture.md); kept for design-history context.

For **Option 1 (Rules-First Document Organizer)**, I would structure the project to support three goals:

1. Keep the MVP simple.
2. Make it easy to add AI classification later.
3. Keep business logic separate from CLI and file handling.

## Recommended Project Structure

```text
project_organizer/
│
├── README.md
├── pyproject.toml
├── requirements.txt
├── .env
│
├── data/
│   ├── config/
│   │   ├── categories.yaml
│   │   ├── filing_rules.yaml
│   │   └── naming_rules.yaml
│   │
│   ├── logs/
│   │
│   └── database/
│       └── organizer.db
│
├── src/
│   └── organizer/
│
│       ├── main.py
│       │
│       ├── cli/
│       │   ├── commands.py
│       │   ├── prompts.py
│       │   └── display.py
│       │
│       ├── core/
│       │   ├── scanner.py
│       │   ├── extractor.py
│       │   ├── classifier.py
│       │   ├── filer.py
│       │   ├── audit.py
│       │   ├── recovery.py
│       │   └── pipeline.py
│       │
│       ├── parsers/
│       │   ├── pdf_parser.py
│       │   ├── docx_parser.py
│       │   ├── txt_parser.py
│       │   ├── markdown_parser.py
│       │   ├── msg_parser.py
│       │   └── eml_parser.py
│       │
│       ├── rules/
│       │   ├── rules_engine.py
│       │   ├── keyword_rules.py
│       │   ├── filename_rules.py
│       │   ├── metadata_rules.py
│       │   └── confidence.py
│       │
│       ├── ai/
│       │   ├── llm_classifier.py
│       │   ├── ollama_provider.py
│       │   ├── openai_provider.py
│       │   ├── anthropic_provider.py
│       │   └── prompts.py
│       │
│       ├── models/
│       │   ├── document.py
│       │   ├── category.py
│       │   ├── classification.py
│       │   ├── audit_event.py
│       │   └── job.py
│       │
│       ├── storage/
│       │   ├── database.py
│       │   ├── audit_repository.py
│       │   ├── file_repository.py
│       │   └── classification_repository.py
│       │
│       ├── services/
│       │   ├── organization_service.py
│       │   ├── review_service.py
│       │   ├── rollback_service.py
│       │   └── reporting_service.py
│       │
│       └── utils/
│           ├── hashing.py
│           ├── logging.py
│           ├── filesystem.py
│           ├── dates.py
│           └── validation.py
│
├── tests/
│   ├── test_scanner.py
│   ├── test_classifier.py
│   ├── test_filer.py
│   ├── test_rules.py
│   └── test_rollback.py
│
└── docs/
    ├── architecture.md
    ├── user_guide.md
    └── development_notes.md
```

***

# Core Processing Flow

```text
CLI
 │
 ▼
Scanner
 │
 ▼
Parser
 │
 ▼
Rules Engine
 │
 ├── High Confidence
 │       │
 │       ▼
 │    Filer
 │
 └── Low Confidence
         │
         ▼
      AI Module
         │
         ▼
       Review
         │
         ▼
        Filer
         │
         ▼
      Audit Log
```

***

# Key Classes

## Document

```python
@dataclass
class Document:
    file_path: Path
    file_name: str
    extension: str
    content: str
    metadata: dict
```

***

## ClassificationResult

```python
@dataclass
class ClassificationResult:
    category: str
    confidence: float
    reason: str
```

***

## AuditEvent

```python
@dataclass
class AuditEvent:
    original_path: str
    new_path: str
    action: str
    timestamp: datetime
```

***

# Database Schema (SQLite)

### documents

```sql
documents
---------
id
file_hash
path
category
confidence
processed_at
```

### file\_moves

```sql
file_moves
----------
id
old_path
new_path
move_date
```

### user\_overrides

```sql
user_overrides
--------------
id
document_id
suggested_category
selected_category
date
```

***

# Filing Rules Example

`categories.yaml`

```yaml
categories:
  requirements:
    keywords:
      - requirement
      - user story
      - acceptance criteria

  architecture:
    keywords:
      - architecture
      - design decision
      - system diagram

  meetings:
    keywords:
      - meeting
      - sprint review
      - retrospective
```

***

# Proposed CLI Commands

## First Scan

```bash
organizer scan \
    --source ./unsorted \
    --output ./projects
```

## Review Queue

```bash
organizer review
```

## Show Audit Log

```bash
organizer audit
```

## Rollback

```bash
organizer rollback \
    --job-id 20260708_001
```

## Reprocess Existing Folder

```bash
organizer rescan
```

***

# Recommended MVP Package Stack

```text
CLI
├─ typer
├─ rich

Models
├─ pydantic

Documents
├─ pymupdf
├─ python-docx
├─ extract-msg

Database
├─ sqlalchemy
├─ sqlite

AI
├─ ollama
├─ openai

Config
├─ pyyaml

Utilities
├─ watchdog
├─ python-dotenv

Testing
├─ pytest
├─ pytest-cov
```

***

## My PM/Architect Recommendation

For Release 1, keep the implementation limited to:

* Folder scanning
* PDF/DOCX/MSG support
* Rules-based classification
* Optional Ollama classification
* SQLite audit trail
* File move history
* Rollback capability
* CLI interface using Typer + Rich

Avoid ChromaDB, vector search, semantic search, and RAG in the MVP. Design the architecture so the future `ai/` and `storage/` layers can be extended later, but don't implement them until real users validate the core document organization workflow.
