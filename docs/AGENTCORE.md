# AgentCore compatibility guidance

AEGIS is structured as a stateless FastAPI/LangGraph application with explicit
provider and tool boundaries. That is compatible with a future containerized
runtime deployment pattern, but no AgentCore resource has been provisioned or
validated.

Before any deployment, verify the target runtime contract, IAM execution role,
network egress, secret injection, request timeout, persistent data strategy,
and Bedrock model access. The local SQLite and Chroma stores are demonstration
stores; a hosted deployment needs durable storage or a startup rebuild.

AEGIS does not use Bedrock Agents Classic.
