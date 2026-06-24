# AskMyDocs AI

## Goal

Build a production-grade Retrieval Augmented Generation platform.

Users can:

- Upload PDF, DOCX, and TXT documents
- Ask questions about uploaded content
- Receive grounded answers with citations
- Manage multiple documents

## Tech Stack

Frontend:
- Next.js 15
- TypeScript
- Tailwind CSS
- Shadcn UI

Backend:
- FastAPI
- Python

AI:
- Gemini 2.5 Flash
- LangChain

Retrieval:
- Hybrid Search
  - BM25
  - Vector Search

Storage:
- PostgreSQL
- Qdrant

## Core Features

### Authentication

- Signup
- Login
- Logout

### Document Upload

- PDF
- DOCX
- TXT

### Knowledge Base

- Chunking
- Embedding generation
- Vector storage

### Chat

- Question answering
- Context retrieval
- Source citations

### Citations

Every answer must reference:

- File name
- Chunk source

## Non Goals

- Voice chat
- Multi-agent systems
- Image generation
- Social features

## Design

Professional SaaS style.

Target audience:
- Enterprises
- Researchers
- Students

Dark theme preferred.

## Deliverables

1. Complete architecture
2. Database schema
3. API design
4. Frontend pages
5. Component structure
6. Development roadmap