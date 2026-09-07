_Last updated: 20260707_

# MVP Concept Option 1: Rules-First Document Organizer

## Positioning

A lightweight, fast, offline-first utility that uses deterministic rules for 80% of classifications and only uses AI when necessary.

**Best for:** Fast MVP, lowest risk, easiest implementation.

***

## Architecture

```text
CLI
 │
 ▼
Folder Scanner
 │
 ▼
Document Extractor
 │
 ├── PDF Parser
 ├── DOCX Parser
 ├── Email Parser
 │
 ▼
Rules Engine
 │
 ├── Naming Rules
 ├── Keyword Rules
 ├── Metadata Rules
 │
 ▼
Classification Engine
 │
 ├── High Confidence
 └── Low Confidence
          │
          ▼
      AI Review
          │
          ▼
    Filing Engine
          │
          ▼
      Audit Log
```

***

## Workflow

### Step 1

User selects source folder.

### Step 2

System recursively scans:

* PDFs
* DOCX
* TXT
* Markdown
* EML
* MSG

### Step 3

Rules classify obvious files.

Examples:

```text
requirements*.docx
→ Requirements

architecture*.pdf
→ Architecture

meeting-notes*
→ Meetings
```

### Step 4

Only uncertain documents are sent to AI.

### Step 5

Files are renamed and moved.

### Step 6

Audit report generated.

***

## Recommended Packages

### Core

```text
typer
rich
pydantic
```

### File Processing

```text
pathlib
watchdog
```

### PDF

```text
pymupdf
pypdf
```

### Word

```text
python-docx
```

### Email

```text
extract-msg
mail-parser
```

### AI

```text
ollama
openai
anthropic
```

### Storage

```text
sqlite3
sqlalchemy
```

***

## Advantages

* Fastest build
* Low AI costs
* High transparency
* Easy debugging

## Weakness

* Intelligence limited by rules

***

# MVP Concept Option 2: AI Classification Workbench

## Positioning

An AI-first local knowledge organizer built around document understanding.

**Best for:** Higher classification accuracy and richer future roadmap.

***

## Architecture

```text
CLI
 │
 ▼
Document Loader
 │
 ▼
Text Extraction
 │
 ▼
Chunking Engine
 │
 ▼
Embedding Engine
 │
 ▼
Vector Store
 │
 ▼
LLM Classification Layer
 │
 ▼
Review Queue
 │
 ▼
Organization Engine
```

***

## Workflow

### Step 1

User points system at project folder.

### Step 2

All documents converted to text.

### Step 3

Embeddings generated.

### Step 4

LLM determines:

* document type
* project relevance
* category
* confidence score

### Step 5

Low-confidence classifications reviewed.

### Step 6

Workspace generated.

***

## Recommended Packages

### Core

```text
typer
rich
pydantic
```

### AI

```text
langchain
llama-index
ollama
openai
anthropic
```

### Embeddings

```text
sentence-transformers
```

### Vector Database

```text
chromadb
faiss
```

### Document Parsing

```text
unstructured
pymupdf
python-docx
```

### Local Models

```text
ollama
llama-cpp-python
```

***

## Advantages

* Better understanding
* Semantic search ready
* RAG ready
* Knowledge graph ready

## Weakness

* More complex
* Increased hardware requirements

***

# MVP Concept Option 3: Project Knowledge Manager

## Positioning

Treat documents as project knowledge rather than files.

The user receives an organized workspace plus a project knowledge base.

**Best for:** Long-term product vision.

***

## Architecture

```text
CLI
 │
 ▼
Ingestion Layer
 │
 ▼
Document Intelligence Layer
 │
 ├── Classification
 ├── Tagging
 ├── Entity Extraction
 ├── Relationship Extraction
 │
 ▼
Knowledge Store
 │
 ├── SQLite
 ├── ChromaDB
 │
 ▼
Workspace Generator
 │
 ▼
Search + Query Engine
```

***

## Workflow

### Step 1

User scans folder.

### Step 2

System extracts:

* topics
* technologies
* requirements
* stakeholders

### Step 3

Documents categorized.

### Step 4

Knowledge index built.

### Step 5

Project workspace generated.

### Step 6

User can ask:

```text
Show all requirements.

Find authentication documents.

What design decisions exist?
```

***

## Recommended Packages

### Extraction

```text
pymupdf
python-docx
extract-msg
unstructured
```

### NLP

```text
spacy
sentence-transformers
```

### Knowledge Layer

```text
chromadb
sqlite
networkx
```

### AI

```text
ollama
openai
anthropic
```

### CLI

```text
typer
rich
textual
```

### Search

```text
whoosh
chromadb
```

***

## Advantages

* Strong product differentiation
* Creates reusable project memory
* Natural evolution into PRD generation
* Natural evolution into RAG

## Weakness

* Largest MVP scope

***

# My Recommendation

As a Product Manager, I would build a hybrid of **Option 1 and Option 3**.

### Release 1 (4–6 weeks)

Build:

* Folder scanning
* PDF/Word/Email ingestion
* Rules-based classification
* Optional LLM classification
* Audit log
* Undo capability
* CLI interface

Packages:

```text
typer
rich
sqlite
pymupdf
python-docx
extract-msg
ollama
openai
pydantic
sqlalchemy
```

### Release 2

Add:

* ChromaDB
* Semantic search
* Project knowledge index

### Release 3

Add:

* PRD generation
* Requirement extraction
* Architecture extraction
* Project scaffolding

This sequence delivers user value immediately while preserving a clear path to the long-term vision of an AI-powered project knowledge and bootstrap platform.
