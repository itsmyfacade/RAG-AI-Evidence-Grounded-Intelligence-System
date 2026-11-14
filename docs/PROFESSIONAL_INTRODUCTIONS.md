# Professional introductions

## A. High-impact introduction

I build evidence-grounded AI applications that connect Python APIs, retrieval systems, structured operational data, and transparent user workflows. In AEGIS, I preserved a constrained FastAPI and LangGraph investigation system, improved lite-profile retrieval from Recall@5 0.6315 to 0.8375 on a 1,200-case synthetic benchmark, and exposed citation, uncertainty, and performance trade-offs instead of presenting unsupported root-cause claims as fact.

## B. LinkedIn or GitHub description

AEGIS is a Python, FastAPI, and LangGraph evidence-grounded investigation system with BM25 retrieval, optional Chroma retrieval, SQLite operational evidence, citation validation, abstention measurement, reproducible benchmarks, and a transparent investigation workbench.

## C. Technical interview introduction

AEGIS is an engineering demonstration I built to study how an AI investigation workflow should handle evidence and uncertainty. The system runs a bounded sequential LangGraph workflow over synthetic technical documents and parameterized SQLite records, returns typed findings and citations, and keeps provider identity visible. I measured the original lite lexical retriever against a BM25-style profile on the same 1,200-case benchmark. Recall@5 improved from 0.6315 to 0.8375, while p95 retrieval latency increased from 1.422 to 2.585 milliseconds locally. The important limitation is that the benchmark is synthetic and the current retrieval-level abstention rate is only 0.2333, so I present the result as measured engineering evidence rather than production accuracy.
