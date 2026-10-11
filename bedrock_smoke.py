from src.rag import search
from src.bedrock import generate_answer

question = "Why would a partner receive HTTP 403 after a deployment?"

print("Retrieving supporting evidence...")
documents = search(question, k=3)

print("Evidence:", [d.metadata["document_id"] for d in documents])
print("Calling the configured AWS Bedrock model...")

answer = generate_answer(question, documents)

print("\nAEGIS INVESTIGATION\n")
print(answer)
