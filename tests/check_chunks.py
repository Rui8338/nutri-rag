import json

with open('data/processed/chunks_debug.json') as f:
    chunks = json.load(f)

for i, c in enumerate(chunks):
    print(f"--- Chunk {i} | Source: {c['source']} | Page: {c['page']} | Chars: {len(c['content'])}")
    print(c['content'])
    print()