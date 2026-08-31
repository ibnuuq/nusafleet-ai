"""Smoke test: project imports, config loads, providers instantiate, schemas validate."""
from src.config import Settings, get_settings
from src.models.llm import GeminiProvider, OllamaProvider, get_llm
from src.models.schemas import Agent, Evidence, EvidenceKind, RunState, Task, TaskResult, Tool


def test_project_imports():
    import src  # noqa: F401
    import src.agents  # noqa: F401
    import src.evidence  # noqa: F401
    import src.memory  # noqa: F401
    import src.orchestrator  # noqa: F401
    import src.tools  # noqa: F401


def test_config_loads(isolated_settings: Settings):
    assert isolated_settings.app_env == "test"
    assert isolated_settings.llm_provider == "ollama"


def test_get_settings_is_cached():
    assert get_settings() is get_settings()


def test_providers_instantiate_without_credentials():
    gemini = GeminiProvider(api_key=None, model="google/gemini-2.5-flash")
    ollama = OllamaProvider(base_url="http://localhost:11434", model="qwen2.5:14b-instruct")
    assert gemini.name == "gemini"
    assert ollama.name == "ollama"


def test_factory_selects_provider(isolated_settings: Settings):
    provider = get_llm("ollama", settings=isolated_settings)
    assert isinstance(provider, OllamaProvider)


def test_schema_validation_works():
    tool = Tool(name="run_sql_readonly", description="Execute a read-only SQL query")
    agent = Agent(
        agent_id="sql-agent",
        name="SQL Agent",
        role="Query the fleet database",
        system_prompt="You answer questions using read-only SQL.",
        allowed_tools=[tool.name],
    )
    task = Task(task_id="t1", description="Find top customers by order count", agent_id=agent.agent_id)
    evidence = Evidence(evidence_id="e1", kind=EvidenceKind.SQL_QUERY, content="SELECT 1", source="sql")
    result = TaskResult(task_id=task.task_id, status="success", output={"rows": 1}, evidence=[evidence])
    run = RunState(run_id="r1", question="Why did cost go up?", tasks=[task], results=[result])

    assert run.tasks[0].task_id == "t1"
    assert run.results[0].evidence[0].kind == EvidenceKind.SQL_QUERY
