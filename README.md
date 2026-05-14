# NutriHub RAG

A nutrition chatbot that combines deterministic tools (TDEE, macros, food database) with RAG over Portuguese and international scientific sources. Built for auditability — every factual answer cites its source.

> **Note:** This project is educational and does not replace professional advice. In Portugal, "nutricionista" is a regulated profession supervised by the Ordem dos Nutricionistas.

---

## Why this project

When asking a generic LLM (ChatGPT, Claude) about nutrition, three problems recur:

1. **No sources** — the answer may be correct, but there is no way to verify it.
2. **No Portuguese context** — DGS recommendations, the INSA food composition table, and local eating habits aren't there.
3. **Knowledge confused with calculation** — when asked to compute calories or convert portions, LLMs hallucinate numbers.

NutriHub RAG addresses these by combining:

- **RAG over scientific sources** — DGS (Roda dos Alimentos), ISSN (athlete protein recommendations), and the Portuguese food distribution program
- **Structured database** with 1,376 foods from the INSA composition table
- **Automatic citations** with source and page number
- **Local LLM via Ollama** — zero costs, data stays on the machine
- **Hybrid agent** — deterministic tools for calculations, RAG for principles, with downstream validation and rule-based routing where the model needs help

---

## Architecture

The system has two flows: **indexing** (runs once to prepare data) and **inference** (runs per user query).

### Inference flow

```mermaid
flowchart TD
    Q[User query] --> R{Pre-router<br/>rule-based}
    R -->|Factual question| RW[LLM Query Rewriter]
    R -->|Other| LLM1[LLM with 4 tool schemas]

    RW --> RAG[Vector search<br/>pgvector + threshold 0.5]
    RAG -->|Chunks found| GEN[LLM generates response<br/>with chunks as context]
    RAG -->|No chunks| NM[/Returns 'not found' message/]

    LLM1 -->|Text response| OUT[/Direct text answer/]
    LLM1 -->|Tool call| V1{Numeric validator}
    V1 -->|Hallucinated| ASK[/Asks for clarification/]
    V1 -->|Valid| V2{Completeness validator}
    V2 -->|Missing required| ASK
    V2 -->|Complete| EXEC[Execute tool]
    EXEC --> GEN

    GEN --> OUT
```

**Key components:**
- **Pre-router** — rule-based detector for factual questions; forces RAG path because Qwen 2.5 3B does not generalize to a 4th tool empirically
- **LLM rewriter** — reformulates conversational queries into technical phrasing for retrieval, with a rule-based fallback
- **2-layer validator** — catches hallucinated numeric args and missing required fields before tool execution
- **4 tools** — `calculate_tdee`, `calculate_macros`, `lookup_food`, `search_nutrition_principles`

### Indexing flow (offline, runs once)

```mermaid
flowchart LR
    PDF[Scientific PDFs] --> EX[pdfplumber<br/>text extraction]
    EX --> CL[Text cleanup<br/>encoding, duplicates]
    CL --> CH[RecursiveCharacterSplitter<br/>500 chars]
    CH --> EM[SentenceTransformer<br/>384 dims]
    EM --> VS[(nutrition.knowledge_chunks<br/>pgvector + HNSW)]

    XL[INSA Excel] --> PD[pandas]
    PD --> DB[(nutrition.foods<br/>1,376 entries)]
```

### Architectural decisions

**Postgres + pgvector instead of Pinecone/Chroma.** INSA table, embeddings, and (eventually) user profiles all live in the same database. Fewer systems to sync, ACID transactions, a single connection. pgvector handles millions of vectors with HNSW indexing — migration to specialized stores only makes sense if scale ever demands it.

**Separation between knowledge and structured data.** The INSA table does not go into the vector store. When the user asks "how many calories in 150g of rice?", the system queries SQL (deterministic computation), not chunks (computation hallucinated by an LLM). RAG is for principles and recommendations; SQL is for numeric facts.

**Multilingual embeddings (384 dim) instead of OpenAI (1536 dim).** The `paraphrase-multilingual-MiniLM-L12-v2` model was trained on 50+ languages including Portuguese. Validated isolated before integration: "proteína para atletas" vs "ingestão proteica desportistas" gave similarity 0.888; "proteína" vs "bolo de chocolate" gave 0.148. 100% source accuracy in the baseline eval confirmed 384 dimensions suffice for this use case.

**Local LLM via Ollama.** Zero cost, no external dependencies, data stays on the machine. Qwen 2.5 3B Instruct chosen over Llama 3.2 3B after the tool calling gate (Day 1): same size, but native function-calling training gave 96% selection accuracy vs 67%.

**Defense in depth over single-component correctness.** The agent has 3 defensive layers (pre-router, validator, threshold filter) that cover specific failure modes of the 3B model. Each layer adds ~50-80 lines but eliminates a class of silent failures.

---

## Stack

**Stack:** Python + PostgreSQL/pgvector + LangChain (retrieval) + local LLM via Ollama. Hybrid agent combining deterministic tools and RAG, deployed without cloud dependencies.

### Languages & environment

- **Python 3.11** with Miniconda

### Database

- **PostgreSQL 15+** with **pgvector** extension
- **SQLAlchemy** as ORM
- **HNSW** index for Approximate Nearest Neighbor search

### RAG pipeline

- **LangChain** — `BaseRetriever` abstraction, text splitters
- **pdfplumber** — PDF text extraction
- **sentence-transformers** — local multilingual embeddings
- **Ollama** — local LLM runtime

### Agent & tools

- **Qwen 2.5 3B Instruct** via Ollama (validated against Llama 3.2 3B in Day 1)
- Custom 2-layer validator (numeric hallucination + required-field completeness)
- Rule-based pre-router for RAG queries
- LLM-based query rewriter with rule-based fallback
- 70+ unit and integration tests with pytest

### Data sources

- **INSA** — Portuguese Food Composition Table (1,376 entries)
- **DGS** — Roda dos Alimentos
- **ISSN** — Position Stand on Protein and Athletic Performance (2017)
- **Programa de Distribuição Alimentar** — portion guidance and food groups

### Models

- **Embeddings:** `paraphrase-multilingual-MiniLM-L12-v2` (384 dim)
- **LLM:** `qwen2.5:3b-instruct` via Ollama (temperature 0.0)

---

## Results

Each phase isolated a specific capability and measured it before composing. Results are honest baselines for a 3B local model — limits are documented rather than hidden.

### Consolidated evaluation

| Phase | Capability under test | Key metric | Result |
|---|---|---|---|
| Day 1 — Tool calling gate | LLM picks correct tool, extracts args, refuses when data missing | Selection / Extraction / Refusal | **96% / 100% / 80%** |
| Phase 1 — RAG baseline | Retrieval finds the right source for factual questions | Source accuracy / Global score | **100% / 71%** |
| Day 3 — Agent loop | LLM routes between 3 deterministic tools + validator catches errors | Routing / Refusal / Validator save | **86.7% / 100% / 100%** |
| Day 4 — RAG as 4th tool | RAG integrated with rewriter + pre-router; retrieves relevant chunks | Routing / Retrieval relevance | **87.5% / 100%** |

> Each row tests an isolated capability rather than overall accuracy. Metrics are designed to diagnose specific failure modes. See the [phase-by-phase documentation](#phase-by-phase-documentation) for detailed analysis.

### Isolated retrieval validation

Before integrating the full pipeline, the embedding model was validated to confirm it distinguishes related from unrelated concepts:

| Comparison | Cosine similarity |
|---|---|
| "proteína para atletas" vs "ingestão proteica desportistas" | **0.888** ✅ |
| "proteína para atletas" vs "receita de bolo" | **0.148** ✅ |

### Sample response

**Query:** "Quanto sódio devo consumir por dia?"

**Query reformulation (LLM rewriter):** "sódio consumo diário recomendado saúde"

**Retrieved sources:**
- `DGS_Roda, p.3` (score 0.758)
- `Distribuicao_Alim, p.20` (score 0.598)
- `Distribuicao_Alim, p.54` (score 0.578)

**Response:**
> According to DGS (Direção-Geral de Saúde) recommendations and other cited sources, daily salt (sodium) consumption should be below 5g. The OMS macronutrient distribution recommendations also apply...

---

## Phase-by-phase documentation

Each phase has detailed documentation in `docs/` (Portuguese, kept as engineering journal):

- [`day1_README.md`](docs/day1_README.md) — Tool calling gate (Llama 3.2 → Qwen 2.5, 5-iteration arc)
- [`day2_README.md`](docs/day2_README.md) — 3 deterministic tools, 70+ tests, bug discovery in food importer
- [`day3_README.md`](docs/day3_README.md) — Agent loop integration with 2-layer validator
- [`day4_README.md`](docs/day4_README.md) — RAG as 4th tool, pre-router, query rewriter

---

## Setup

### Prerequisites

- Python 3.11+
- Miniconda or Anaconda
- PostgreSQL 15+ with the `pgvector` extension
- [Ollama](https://ollama.com/) installed locally

### 1. Clone

```bash
git clone https://github.com/Rui8338/nutri-rag.git
cd nutri-rag
```

### 2. Python environment

```bash
conda create -n nutrihub python=3.11
conda activate nutrihub
pip install -r requirements.txt
```

### 3. Postgres setup

Create database and extension:

```bash
createdb nutrihub_rag
psql nutrihub_rag
```

Inside psql:

```sql
CREATE EXTENSION vector;
CREATE SCHEMA nutrition;

CREATE TABLE nutrition.foods (
    id SERIAL PRIMARY KEY,
    name VARCHAR(255) NOT NULL UNIQUE,
    portion_size_g DECIMAL(10, 2),
    calories DECIMAL(10, 2),
    protein_g DECIMAL(10, 2),
    carbs_g DECIMAL(10, 2),
    fat_g DECIMAL(10, 2),
    fiber_g DECIMAL(10, 2),
    sodium_mg DECIMAL(10, 2),
    water_g DECIMAL(10, 2),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE nutrition.knowledge_chunks (
    id SERIAL PRIMARY KEY,
    source VARCHAR(100) NOT NULL,
    content TEXT NOT NULL,
    embedding vector(384),
    page_number INT,
    chunk_index INT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_knowledge_chunks_embedding
ON nutrition.knowledge_chunks
USING HNSW (embedding vector_cosine_ops);
```

### 4. Environment variables

Create a `.env` file at the root:

```ini
DATABASE_URL=postgresql://postgres:password@localhost:5432/nutrihub_rag
LOG_LEVEL=INFO
```

### 5. Download the local LLM

```bash
ollama pull qwen2.5:3b-instruct
```

### 6. Import data

Place source files in `data/sources/`:

- `INSA_Tabela_Composicao.xlsx`
- `DGS_Roda_Alimentos.pdf`
- `ISSN_Protein_Athletic_Performance_2017.pdf`
- `Programa_Distribuicao_Alimentos.pdf`

Import the INSA food table:

```bash
python -m src.ingestion.food_importer
```

Process PDFs and generate embeddings:

```bash
python -m src.embeddings.embedding_store
```

### 7. Run

Direct query (single turn):

```bash
python -c "from src.agent.loop import run_agent; print(run_agent('Quais são os benefícios da fibra alimentar?').text)"
```

Run the test suite:

```bash
pytest tests/
```

Run an evaluation:

```bash
python -m experiments.eval_day4
```

---

## Roadmap

### Phase 1 — RAG Foundation ✅

- Environment setup and project structure
- Postgres with pgvector and complete schema
- INSA composition table import (1,376 foods)
- PDF ingestion and cleanup (592 chunks)
- Multilingual embeddings and indexing
- Custom LangChain retriever
- RAG chain with automatic citations
- Baseline eval: 71% global, 100% source accuracy

### Phase 2 — Agent + Tools ✅

- Tool calling gate validation (Llama 3.2 3B → Qwen 2.5 3B, 5-iteration arc)
- 3 deterministic tools (TDEE, macros, food lookup) with 70+ unit tests
- Single-step agent loop with 2-layer downstream validator
- RAG integrated as 4th tool via rule-based pre-router + LLM query rewriter
- Discovery and documentation of Qwen 3B structural limits

### Phase 3 — Production Readiness (future)

- Larger LLM (Qwen 2.5 7B) — eliminate need for rule-based routing, improve context fidelity
- Multi-step agent (composed queries: "calculate TDEE then macros")
- User profile persistence in Postgres
- Conversational memory across turns
- UI with Chainlit or Streamlit
- Containerized deployment (Docker Compose or Railway/Fly.io)

### Phase 4 — Beyond MVP (further future)

- Expanded corpus (clinical nutrition, sport periodization, specific conditions)
- Multilingual response generation
- Tool composition planning (multi-tool single-turn)
- A/B testing infrastructure for prompt variants

---

## Known limitations

**Not a nutritionist.** The system is educational. Personalized recommendations, clinical meal plans, and disease management require a qualified professional.

**3B model structural limits.** Empirically validated:
- Does not generalize to a 4th tool via prompting alone (mitigated by rule-based pre-router)
- Sensitive to syntactic structure of queries (Day 3 — `"I have X..."` vs `"How many calories should I eat?"`)
- Residual variability even at `temperature=0` for boundary queries (Day 4 — salmon query oscillates between runs)
- Can ignore context chunks when generating final response (Day 4 — R3 failure mode)

These are not bugs but operational characteristics of small local models. Phase 3 will evaluate whether a larger model (Qwen 2.5 7B) eliminates them.

**Limited corpus coverage.** Only 3 scientific PDFs. Advanced supplementation, specific conditions (diabetes, renal, pregnancy), and detailed sport periodization are not covered.

**Encoding artifacts in source PDFs.** Original PDFs had encoding issues. The pragmatic solution was to remove accents during cleanup ("PORÇÃO" → "PORCAO"). Semantic information is intact for RAG; surface inconsistencies remain.

**Mixed language in sources.** The ISSN paper is in English; DGS sources are in Portuguese. The LLM responds in Portuguese but may include technical English terms when citing the paper.

**No persistent memory.** Each query is independent. No profile, no history, no personalization. Planned for Phase 3.

**No fact verification.** The system trusts indexed sources 100%. If a source is outdated (the Roda dos Alimentos is from 2016), the system has no way to know.

**Citation specificity.** The 3B model often cites generically ("according to scientific literature") rather than specifically ("Distribuicao_Alim, p.21"). A larger model would cite specifically.

**Factual query latency.** ~6-10s per factual query (rewriter + retrieval + generation). Acceptable for chat; problematic for real-time use cases.

---

## Lessons learned

Eight lessons consolidated from Phase 1 and Phase 2.

**1. RAG is not "PDFs in a vector store."** Most of the effort went into chunking, text cleanup, and embedding calibration — not into the LLM. When RAG fails in production, it is almost always in the data, rarely in the model.

**2. Validate components in isolation before integrating.** The initially chosen embedding model (`all-MiniLM-L6-v2`) gave 0.214 similarity between related phrases and 0.202 between unrelated phrases in Portuguese. Detecting this in isolation saved hours of debugging an integrated pipeline. Same principle applied in Day 1 (tool calling gate before agent loop) and Day 2 (deterministic tools with unit tests before LLM integration).

**3. Structured data does not belong in the vector store.** The INSA table has exact nutritional compositions. If they were chunks, the LLM would have to "read" and compute — guaranteed hallucinations. In SQL, it is deterministic. RAG is for principles; SQL is for numeric facts.

**4. Source accuracy > answer accuracy.** The baseline eval showed 100% source accuracy but 71% global score. Retrieval works perfectly; failures are in generation and in the eval's keyword calibration. Knowing how to distinguish these is critical for iterating on the right component.

**5. Prompt engineering has a ceiling, and the ceiling is the model.** Day 1 showed Llama 3.2 3B could not reach the refusal gate regardless of prompt iterations (4 attempts, 0% in category D every time). Switching to Qwen 2.5 3B unlocked it. Day 4 showed Qwen 2.5 3B does not generalize to a 4th tool regardless of few-shot iterations. Recognize the ceiling and choose between accepting it, mitigating around it, or changing the model.

**6. Defense in depth works for LLM systems.** The final agent has 3 defensive layers (pre-router, 2-layer validator, retrieval threshold). Each covers a specific failure mode. Cost: ~250 lines. Benefit: 2 of 3 known failure modes are caught structurally rather than silently producing wrong output.

**7. `temperature=0` exposes determinism — both its presence and its absence.** Day 3 confirmed determinism enables disciplined iteration. Day 4 also confirmed that even at `temperature=0`, Ollama state affects boundary queries. The model is determinist*ic* about most queries but not about all of them. Knowing this distinction prevents chasing phantom bugs.

**8. Test sets should reflect the domain, not the system.** Day 4's X1 case ("How many calories does salmon have?") seemed reasonable until investigation revealed the INSA table has 3 salmon variants with 47 kcal difference. The system's behavior (ask for clarification) was correct; the test was miscalibrated. Calibrating tests to the system is an anti-pattern; calibrating tests to the domain is design.

---

## References

- [DGS — Direção-Geral da Saúde](https://www.dgs.pt/)
- [INSA — Instituto Nacional de Saúde Doutor Ricardo Jorge](https://portfir-insa.min-saude.pt/)
- [ISSN Position Stand on Protein and Athletic Performance (2017)](https://jissn.biomedcentral.com/articles/10.1186/s12970-017-0177-8)
- [pgvector](https://github.com/pgvector/pgvector)
- [LangChain](https://python.langchain.com/)
- [Ollama](https://ollama.com/)
- [sentence-transformers](https://www.sbert.net/)
- [Qwen 2.5](https://github.com/QwenLM/Qwen2.5)