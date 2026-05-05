# NutriHub RAG

Um chatbot que responde a perguntas sobre nutrição com base em fontes científicas portuguesas e internacionais, sempre a citar de onde vem a informação.

> **Aviso:** Este projeto é apenas educacional e não substitui o aconselhamento de um nutricionista. Em Portugal, "nutricionista" é uma profissão regulamentada pela Ordem dos Nutricionistas.

---

## Porquê este projeto

Quando se faz uma pergunta sobre nutrição a um LLM como o ChatGPT ou Claude, há três problemas que aparecem sempre:

1. **As respostas não têm fontes** — pode estar tudo certo, mas não há forma de verificar.
2. **Falta contexto português** — as recomendações da DGS, a Tabela do INSA e os hábitos alimentares locais não estão lá.
3. **Os modelos confundem conhecimento com cálculo** — quando lhes pedem para somar calorias ou converter porções, inventam números.
O NutriHub RAG resolve estes problemas combinando:

- **RAG sobre fontes científicas** — DGS (Roda dos Alimentos), ISSN (recomendações para atletas) e o programa de distribuição alimentar
- **Base de dados estruturada** com 1377 alimentos da Tabela de Composição do INSA
- **Citações automáticas** em todas as respostas, com fonte e página
- **LLM local** via Ollama (Llama 3.2) — sem custos e sem dados a sair da máquina

---

## Arquitetura

O sistema tem dois fluxos: **indexação** (corre uma vez para preparar os dados) e **inferência** (corre sempre que o utilizador pergunta algo).

### Fluxo de indexação (offline)

```
PDFs científicos              Tabela INSA
       ↓                           ↓
   pdfplumber                 pandas
       ↓                           ↓
Limpeza de texto         Importação direta
(encoding, duplicados)            ↓
       ↓                   nutrition.foods
RecursiveCharacterSplitter      
(chunks de 500 chars)            
       ↓                         
SentenceTransformer              
(384 dimensões)                  
       ↓                         
nutrition.knowledge_chunks       
(pgvector + índice HNSW)         
```

### Fluxo de inferência (online)

```
Pergunta do utilizador
        ↓
Embedding da pergunta (mesmo modelo)
        ↓
Similarity search no pgvector (top 5 chunks)
        ↓
Contexto montado com fonte e página
        ↓
LLM (Llama 3.2 via Ollama)
        ↓
Resposta + citações
```

### Decisões arquiteturais

**Postgres + pgvector em vez de Pinecone/Chroma**
A Tabela INSA, os embeddings, e (mais tarde) os perfis de utilizador vivem todos na mesma base de dados. Menos sistemas para sincronizar, transações ACID, e uma única ligação. pgvector aguenta milhões de vetores com índice HNSW — só faz sentido migrar quando isso se tornar real.

**Separação entre conhecimento e dados estruturados**
A Tabela INSA não vai para o vector store. Quando o utilizador pergunta "quantas calorias tem 150g de arroz", o sistema vai consultar SQL (cálculo determinístico), não chunks (cálculo alucinado pelo LLM). Esta decisão é fundamental — RAG é para princípios e recomendações, SQL é para factos numéricos.

**Embeddings multilingues (384 dim) em vez de OpenAI (1536 dim)**
O modelo `paraphrase-multilingual-MiniLM-L12-v2` foi treinado em 50+ línguas, incluindo português. Foi validado isoladamente antes da integração: "proteína para atletas" vs "ingestão proteica desportistas" deu similaridade de 0.888, enquanto "proteína" vs "bolo de chocolate" deu 0.148. Score de retrieval de 100% nos evals confirmou que 384 dimensões chegam para este caso de uso.

**LLM local via Ollama**
Sem custos, sem dependências externas, dados ficam na máquina do utilizador. Llama 3.2 (3B parâmetros) provou ser suficiente — o que define a qualidade do RAG é o retrieval, não o tamanho do LLM.

---

## Stack

### Linguagem e ambiente

- **Python 3.11**
- **Miniconda** para gestão do ambiente

### Base de dados

- **PostgreSQL 15+** com extensão **pgvector** para similarity search
- **SQLAlchemy** como ORM
- Índice **HNSW** para Approximate Nearest Neighbor search

### RAG Pipeline

- **LangChain** — orquestração e abstrações (BaseRetriever, text splitters)
- **pdfplumber** — extração de texto de PDFs
- **sentence-transformers** — embeddings locais multilingues
- **Ollama** — runtime para LLM local

### Modelos

- **Embeddings:** `paraphrase-multilingual-MiniLM-L12-v2` (384 dim)
- **LLM:** `llama3.2:3b` via Ollama

### Fontes de dados

- **DGS** — Roda dos Alimentos
- **ISSN** — Position Stand on Protein and Athletic Performance (2017)
- **Programa de Distribuição Alimentar** — porções e grupos alimentares
- **INSA** — Tabela de Composição de Alimentos (1377 alimentos)

---

## Resultados

### Estatísticas do sistema

| Métrica                  | Valor               |
| ------------------------- | ------------------- |
| Documentos processados    | 3 PDFs científicos |
| Chunks indexados          | 592                 |
| Alimentos na BD           | 1377                |
| Dimensões dos embeddings | 384                 |
| Latência de retrieval    | <500ms              |

### Validação isolada do retrieval

Antes de integrar todo o pipeline, o modelo de embeddings foi validado isoladamente para confirmar que distinguia conceitos relacionados de não relacionados:

| Comparação                                                  | Cosine Similarity  |
| ------------------------------------------------------------- | ------------------ |
| "proteína para atletas" vs "ingestão proteica desportistas" | **0.888** ✅ |
| "proteína para atletas" vs "receita de bolo"                 | **0.148** ✅ |

### Eval set — baseline

10 queries em diferentes categorias (athletic_nutrition, food_portions, micronutrients, food_groups, nutrient_timing, macronutrients), com scoring ponderado:

- **60%** keywords match (informação correta na resposta)
- **40%** source match (fonte correta citada)| Métrica                  | Resultado              |
  | ------------------------- | ---------------------- |
  | Score global              | **71%**          |
  | PASS (≥70%)              | 7/10                   |
  | PARTIAL (50-69%)          | 3/10                   |
  | FAIL (<50%)               | 0/10                   |
  | **Source accuracy** | **100% (10/10)** |

**Source accuracy de 100%** significa que o retrieval encontra sempre a fonte correta para cada pergunta — o que é o componente mais crítico de um sistema RAG. Os PARTIALs têm origem em queries sobre nutrição desportiva onde os chunks vêm em inglês (paper do ISSN) e o LLM responde em português, criando ligeiras divergências de keywords.

### Exemplo de resposta

**Query:** "quanto sal se deve comer por dia?"

**Resposta:**

> De acordo com a fonte DGS_Roda (página 3), a quantidade de sal (cloreto de sódio - NaCl) que deve ser consumida por dia é inferior a 5g.

**Citações:** `DGS_Roda (p.3)`, `DGS_Roda (p.2)`, `Distribuicao_Alim (p.27)`

---

## Setup

### Pré-requisitos

- Python 3.11+
- Miniconda ou Anaconda
- PostgreSQL 15+ com extensão `pgvector`
- [Ollama](https://ollama.com/) instalado

### 1. Clonar o repositório

```bash
git clone https://github.com/<teu-username>/nutri-rag.git
cd nutri-rag
```

### 2. Criar ambiente Python

```bash
conda create -n nutrihub python=3.11
conda activate nutrihub
pip install -r requirements.txt
```

### 3. Configurar Postgres

Cria a base de dados e a extensão:

```bash
createdb nutrihub_rag
psql nutrihub_rag
```

Dentro do psql:

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

### 4. Configurar variáveis de ambiente

Cria um ficheiro `.env` na raiz:

```ini
DATABASE_URL=postgresql://postgres:password@localhost:5432/nutrihub_rag
LOG_LEVEL=INFO
```

### 5. Descarregar o LLM local

```bash
ollama pull llama3.2:3b
```

### 6. Importar dados

Coloca os ficheiros das fontes em `data/sources/`:

- `INSA_Tabela_Composicao.xlsx`
- `DGS_Roda_Alimentos.pdf`
- `ISSN_Protein_Athletic_Performance_2017.pdf`
- `Programa_Distribuicao_Alimentos.pdf`
  Importa a Tabela INSA:

```bash
python -m src.ingestion.food_importer
```

Processa os PDFs e gera embeddings:

```bash
python -m src.embeddings.embedding_store
```

### 7. Testar

Pergunta diretamente:

```bash
python -m src.rag.chain
```

Correr o eval set completo:

```bash
python tests/test_rag.py
```

---

## Roadmap

### Semana 1 — Pipeline RAG (concluída)

- [X] Setup do ambiente e estrutura do projeto
- [X] Postgres com pgvector e schema completo
- [X] Importação da Tabela INSA (1377  alimentos)
- [X] Ingestão e limpeza de PDFs (592 chunks)
- [X] Embeddings multilingues e indexação
- [X] Custom retriever em LangChain
- [X] RAG chain com citações automáticas
- [X] Eval set com 10 queries — baseline 71%

### Semana 2 — Tools e Agent

- [ ] Function calling para cálculos determinísticos
  - `calculate_tdee(perfil)` — Mifflin-St Jeor
  - `calculate_macros(tdee, objetivo)` — proteína, carbs, gorduras
  - `lookup_food(nome)` — consulta direta à Tabela INSA
  - `log_meal(alimentos, quantidades)` — somar nutrientes da refeição
- [ ] Agent loop — LLM decide entre RAG e tools
- [ ] Perfil de utilizador persistido em Postgres
- [ ] Eval set expandido (20+ queries com tools)

### Semana 3 — Interface e Deploy

- [ ] UI com Chainlit ou Streamlit
- [ ] Dashboard de macros do dia
- [ ] Histórico de conversas
- [ ] Deploy (Railway / Fly.io)
- [ ] Demo em vídeo

---

## Limitações conhecidas

**Não é um nutricionista**
O sistema é educacional. Recomendações personalizadas, planos alimentares clínicos, e gestão de patologias requerem um nutricionista qualificado.

**Cobertura de fontes limitada**
Apenas 3 PDFs científicos. Áreas como suplementação avançada, nutrição em condições específicas (diabetes, doença renal, gravidez), ou periodização desportiva detalhada não estão cobertas.

**Caracteres especiais perdidos no parsing**
Os PDFs originais tinham problemas de encoding. A solução pragmática foi remover acentos durante a limpeza ("PORÇÃO" → "PORCAO"). A informação semântica fica intacta para o RAG mas as respostas podem ter algumas inconsistências visuais.

**Mistura de idiomas nas fontes**
O paper do ISSN é em inglês, as fontes da DGS são em português. O LLM responde sempre em português mas pode misturar termos técnicos ingleses quando cita o paper.

**Sem memória entre conversas**
Cada query é independente. Não há perfil, não há histórico, não há personalização. Pretende-se resolver esta limitação na Semana 2

**Sem verificação de factos**
O sistema confia 100% nas fontes indexadas. Se uma fonte estiver desatualizada (a Roda dos Alimentos é de 2016), o sistema não tem como saber.

---

## Lições aprendidas

Para além do código, este projeto consolidou várias lições de AI engineering:

**1. RAG não é só "PDFs num vector store"**
A maior parte do esforço esteve em chunking, limpeza de texto, e calibração de embeddings — não no LLM. Quando o RAG falha em produção, é quase sempre nos dados, raramente no modelo.

**2. Validar componentes isolados antes de integrar**
O modelo de embeddings inicialmente escolhido (`all-MiniLM-L6-v2`) dava similaridade de 0.214 entre frases relacionadas e 0.202 entre frases não relacionadas em português. Detectar isto isoladamente poupou horas de debugging num pipeline integrado.

**3. Dados estruturados não devem viver no vector store**
A Tabela INSA tem composições nutricionais exatas. Se fossem chunks, o LLM teria de "ler" e calcular — alucinações garantidas. Em SQL, é determinístico.

**4. Source accuracy > Answer accuracy**
O eval mostrou source accuracy de 100% mas score global de 71%. O retrieval funciona perfeitamente; as falhas são na geração e na calibração das keywords do eval. Saber distinguir isto é crítico para iterar no sistema certo.

**5. Evals revelam mais sobre o eval do que sobre o sistema**
O score subiu de 55% para 71% sem mudar uma linha de código do RAG — apenas calibrando o eval set. Um eval mal feito mente sobre a qualidade do sistema.

**6. Engenharia é trade-offs explícitos**
Cada decisão arquitetural teve um trade-off conhecido: 384 dim vs 1536, LLM local vs API, remover acentos vs reparar encoding. Tornar os trade-offs explícitos permite revisitá-los quando o contexto muda.

---

## Referências

- [DGS — Direção-Geral da Saúde](https://www.dgs.pt/)
- [INSA — Instituto Nacional de Saúde Doutor Ricardo Jorge](https://portfir-insa.min-saude.pt/)
- [ISSN Position Stand on Protein and Athletic Performance (2017)](https://jissn.biomedcentral.com/articles/10.1186/s12970-017-0177-8)
- [pgvector](https://github.com/pgvector/pgvector)
- [LangChain](https://python.langchain.com/)
- [Ollama](https://ollama.com/)
- [sentence-transformers](https://www.sbert.net/)