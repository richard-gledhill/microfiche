_Last updated: 20260707_

That's a better fit for the product vision.

If the primary goal is to **organize documents into an existing project library** rather than build a document management system, then SQLite should be reduced to an optional audit/cache component and **the folder structure becomes the source of truth**.

## Revised Architecture

Instead of:

```text
Documents
    ↓
Database
    ↓
Organization
```

Use:

```text
Documents
    ↓
Classification
    ↓
Library Folder Structure
    ↓
Audit Logs
```

The filesystem itself represents the knowledge model.

***

# Revised Project Structure

```text
project_organizer/
│
├── README.md
├── pyproject.toml
├── requirements.txt
│
├── config/
│   ├── categories.yaml
│   ├── filing_rules.yaml
│   ├── naming_rules.yaml
│   └── library_templates.yaml
│
├── logs/
│   ├── organization.log
│   ├── audit.log
│   └── rollback/
│
├── src/
│   └── organizer/
│
│       ├── main.py
│
│       ├── cli/
│       │   ├── commands.py
│       │   ├── review.py
│       │   └── display.py
│
│       ├── core/
│       │   ├── scanner.py
│       │   ├── extractor.py
│       │   ├── classifier.py
│       │   ├── filer.py
│       │   ├── organizer.py
│       │   ├── library_builder.py
│       │   └── rollback.py
│
│       ├── parsers/
│       │   ├── pdf_parser.py
│       │   ├── docx_parser.py
│       │   ├── markdown_parser.py
│       │   ├── txt_parser.py
│       │   ├── msg_parser.py
│       │   └── eml_parser.py
│
│       ├── rules/
│       │   ├── rules_engine.py
│       │   ├── keyword_rules.py
│       │   ├── metadata_rules.py
│       │   └── confidence.py
│
│       ├── ai/
│       │   ├── llm_classifier.py
│       │   ├── ollama_provider.py
│       │   ├── openai_provider.py
│       │   └── prompts.py
│
│       ├── library/
│       │   ├── templates.py
│       │   ├── categories.py
│       │   ├── naming.py
│       │   └── folder_mapping.py
│
│       ├── models/
│       │   ├── document.py
│       │   ├── category.py
│       │   └── classification.py
│
│       └── utils/
│           ├── filesystem.py
│           ├── hashing.py
│           ├── logging.py
│           └── validation.py
│
└── tests/
```

***

# Library Structure as the System of Record

The product organizes files into a predefined library.

Example:

```text
Projects/
│
├── Project Phoenix/
│
│   ├── 01 Requirements/
│   │   ├── Business Requirements
│   │   ├── User Stories
│   │   └── Acceptance Criteria
│   │
│   ├── 02 Architecture/
│   │   ├── Diagrams
│   │   ├── ADRs
│   │   └── Technical Design
│   │
│   ├── 03 Research/
│   │
│   ├── 04 Meeting Notes/
│   │
│   ├── 05 Correspondence/
│   │
│   ├── 06 Reference Material/
│   │
│   └── 99 Archive/
```

This structure becomes the knowledge library.

No database lookup is required to find documents.

***

# Filing Engine

Instead of storing metadata in tables:

```text
Document
    ↓
Classify
    ↓
Map Category
    ↓
Move File
```

Example mapping:

```python
CATEGORY_MAP = {
    "requirements":
        "01 Requirements",

    "architecture":
        "02 Architecture",

    "research":
        "03 Research",

    "meetings":
        "04 Meeting Notes",

    "correspondence":
        "05 Correspondence"
}
```

***

# Library Templates

Support multiple project types.

```yaml
templates:

  software_project:
    - Requirements
    - Architecture
    - Research
    - Meeting Notes
    - Correspondence
    - Reference Material

  ai_project:
    - Requirements
    - Architecture
    - Prompts
    - Models
    - Research
    - Meeting Notes

  personal_project:
    - Ideas
    - Research
    - Notes
    - Archive
```

CLI:

```bash
organizer create-library \
  --template software_project \
  --name project-phoenix
```

***

# Metadata Storage

Instead of a database, use sidecar files.

Example:

```text
architecture_review.docx

architecture_review.metadata.json
```

```json
{
  "category": "Architecture",
  "confidence": 0.92,
  "classified_by": "rules_engine",
  "processed_date": "2026-07-08"
}
```

Benefits:

* Human readable
* Portable
* Git-friendly
* No database maintenance

***

# Audit and Rollback

Store operations as files.

```text
logs/
│
├── audit.log
│
└── rollback/
    ├── job_001.json
    ├── job_002.json
```

Example:

```json
{
  "job_id": "job_001",
  "moves": [
    {
      "from": "Inbox/spec.docx",
      "to": "Project/01 Requirements/spec.docx"
    }
  ]
}
```

Rollback:

```bash
organizer rollback job_001
```

***

# Updated Processing Flow

```text
Source Folder
      │
      ▼
 File Scanner
      │
      ▼
 Document Parser
      │
      ▼
 Rules Engine
      │
      ├─ High Confidence
      │          │
      │          ▼
      │     Library Folder
      │
      └─ Low Confidence
                 │
                 ▼
           LLM Review
                 │
                 ▼
          File Organizer
                 │
                 ▼
          Audit Log
```

***

# Recommended MVP Packages

```text
CLI
├── typer
├── rich

Document Parsing
├── pymupdf
├── python-docx
├── extract-msg

Configuration
├── pyyaml
├── pydantic

AI
├── ollama
├── openai

Utilities
├── watchdog
├── python-dotenv
```

### Removed from MVP

```text
sqlalchemy
sqlite
chromadb
faiss
langchain
llama-index
```

***

## PM/Architect Recommendation

For the first release, treat the **folder hierarchy as the product**.

A successful user outcome is not:

> "The document is stored in a database."

It is:

> "My chaotic collection of files has been transformed into a clean, navigable project library that I can browse with Windows Explorer, OneDrive, SharePoint, Git, or any file manager."

That keeps the MVP simple, transparent, portable, and aligned with how developers already manage project documentation.
