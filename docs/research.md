# Framework research and decisions

Research date: **20 October 2026**. Official documentation, GitHub repository metadata/releases and PyPI metadata were checked before implementation.

## What the workflow needs

The process has known steps: query TeamCity, correlate revisions and PRs, retrieve Jira context, create an isolated Git worktree, rebase, reproduce a failure, propose a small edit, build and test, and publish a verified suggestion. The uncertain part is the diagnosis and source edit. Compilation, test discovery, Git operations and publication need explicit code and recorded outcomes.

An orchestration framework should make these steps and their failure branches easy to inspect and change. It must accept the existing token-authenticated OpenAI-compatible Qwen endpoint, work on a Windows C++ worker, and preserve useful local state without requiring a hosted control plane.

## Compared options

| Option | Current Python version | GitHub stars at research time | Strengths for this project | Tradeoff |
| --- | --- | ---: | --- | --- |
| **LangGraph** | **1.2.16** | **43,583** | Explicit state, named nodes, conditional edges, loops, local checkpoints; can use ordinary Python functions and any model client | More wiring than a role/task decorator, but the sequence is visible |
| CrewAI | 1.15.28 | 59,918 | Accessible role/task agents; Flows support routing and SQLite state persistence; custom model base URLs | Both crew and flow abstractions are available; this starter only needs a small explicit graph |
| Microsoft Agent Framework | 1.22.0 | 14,229 | Modern successor to AutoGen/Semantic Kernel, Python and .NET, workflows and checkpoints, custom OpenAI base URL | A credible alternative, especially for a .NET-led team; a smaller public repository community at this snapshot |
| PydanticAI | 2.58.0 | 20,755 | Typed agents, custom OpenAI-compatible providers, graph support, durable execution integrations | Advanced durable execution adds another runtime choice; unnecessary for the initial single worker |

Stars were fetched with `gh api repos/{owner}/{repo}` on the research date. They measure public interest, **not production installations, reliability or market share**. All four repositories declared the MIT license. Versions were read from PyPI JSON metadata and checked against official release pages. These are a dated comparison, not floating installation requirements; `uv.lock` fixes the implementation's dependency versions.

Sources: [LangGraph repository](https://github.com/langchain-ai/langgraph), [CrewAI repository](https://github.com/crewAIInc/crewAI), [Microsoft Agent Framework repository](https://github.com/microsoft/agent-framework), [PydanticAI repository](https://github.com/pydantic/pydantic-ai). Release pages: [LangGraph](https://github.com/langchain-ai/langgraph/releases), [CrewAI 1.15.28](https://github.com/crewAIInc/crewAI/releases/tag/1.15.28), [Agent Framework Python 1.22.0](https://github.com/microsoft/agent-framework/releases/tag/python-1.22.0), [PydanticAI 2.58.0](https://github.com/pydantic/pydantic-ai/releases/tag/v2.58.0).

## Decision: LangGraph, with a small model adapter

LangGraph supports a mixture of deterministic functions and model-driven steps, without requiring LangChain's higher-level agent abstraction. A state graph makes the retry budget and publish conditions explicit. This is a fit decision for this particular workflow; it does not establish that LangGraph is universally better than the alternatives. [Official overview](https://docs.langchain.com/oss/python/langgraph/overview), [graph API](https://docs.langchain.com/oss/python/langgraph/graph-api).

The starter uses LangGraph for orchestration and a thin `httpx` adapter for the endpoint's standard Chat Completions interface. LangChain's `ChatOpenAI` also accepts a custom `base_url` and API key; its documentation cautions that nonstandard provider response fields are outside its scope. The thin client keeps the required wire format small and avoids assuming that the private Qwen service supports native tools or server-side strict structured output. Pydantic validates the proposed edit payload locally. [ChatOpenAI compatibility and configuration](https://docs.langchain.com/oss/python/integrations/chat/openai).

The framework cannot determine this private endpoint's actual model identifier, context length, reasoning options or compatibility. Those remain configuration and integration-test concerns. The sample model string is a placeholder to replace with the deployment's served identifier.

## State, operations and Windows

The single-worker MVP uses file-backed SQLite checkpoints and a separate local execution/publication record. LangGraph documents SQLite for local development and PostgreSQL for production persistence. Checkpoints record graph progress; external Git pushes and PR creation still need application-level receipts and reconciliation. This version keeps those boundaries explicit and does not advertise transparent resumption of every interrupted native process. [Persistence documentation](https://docs.langchain.com/oss/python/langgraph/persistence).

The tool runs as a Python CLI on the Windows worker that already has the C++ toolchain and network access. It uses argv arrays, isolated Git worktrees and PowerShell scheduling wrappers. No Docker, Linux subsystem, LangSmith account or hosted agent server is required. Logs and evidence stay local; model and API traffic use the configured URLs.

Windows suitability is an architectural assessment, backed by this repository's Windows CI when that run passes. It is not an upstream test guarantee: LangGraph's core test workflow currently uses Ubuntu for its Python-version matrix. [Upstream core CI](https://github.com/langchain-ai/langgraph/blob/main/.github/workflows/_test_langgraph.yml). The project therefore runs its own tests and actual C++ demo on `windows-latest` and `ubuntu-latest`.

Before production operation, exercise the real solution, test-name mapping, internal CA chain, Git credentials, endpoint output, server versions and permissions on the actual Windows worker. The bundled demo proves the synthetic integration and native sample build; it cannot prove access to systems whose URLs and tokens were not provided.

## Why the alternatives remain viable

CrewAI has the largest star count in this comparison and offers approachable role/task agents. Its Flows provide state, branching and SQLite persistence, so it could implement this workflow. We chose the more direct graph representation because most steps are fixed integrations and compiler operations. Custom OpenAI-compatible endpoints are documented. CrewAI also documents an explicit telemetry-disable environment setting. [Flows](https://docs.crewai.com/en/concepts/flows), [model connections](https://docs.crewai.com/en/learn/llm-connections), [telemetry configuration](https://github.com/crewAIInc/crewAI/blob/main/lib/crewai/README.md).

Microsoft Agent Framework is a current stable Python option at this date, with both graph and functional workflows. Its checkpointing supports saved workflow state. The OpenAI integration exposes a separate Chat Completions client and a custom base URL, making a Qwen deployment possible without Azure. It deserves another evaluation if .NET integration becomes a primary requirement. [Overview](https://learn.microsoft.com/agent-framework/overview/?pivots=programming-language-python), [checkpoints](https://learn.microsoft.com/agent-framework/workflows/checkpoints), [OpenAI client configuration](https://github.com/microsoft/agent-framework/blob/main/python/packages/openai/README.md).

PydanticAI is attractive for strongly typed agent inputs and outputs and supports other OpenAI-compatible providers. Durable execution can integrate Temporal, DBOS, Prefect, Restate and other engines; that flexibility adds deployment choices this starter does not need. Pydantic's data validation is still used independently. [Models and providers](https://pydantic.dev/docs/ai/models/overview/), [durable execution](https://pydantic.dev/docs/ai/capabilities/durable_execution/overview/).

## Deliberate limits

The initial workflow makes a suggestion via a PR and does not merge it. It repairs configured source paths with a bounded number of attempts, verifies a full configured suite and repeats verification after the final rebase. The example build commands cleanly rebuild sources to avoid stale incremental binaries. Test identities include their XML classname when distinct, preserving GoogleTest fixture identity. It stops when a failure cannot be reproduced or safely verified. Repositories using Git submodules are currently rejected.

Screenshot evidence consists of links to existing TeamCity artifacts; producing screenshots for a specific UI product needs a dedicated capture adapter. A distributed scheduler, fleet management and automatic conflict resolution are future requirements rather than implemented features.
