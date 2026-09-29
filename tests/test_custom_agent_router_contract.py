import re
import tomllib
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
ROUTER = REPO_ROOT / "skills" / "custom-agent-router"
SKILL = ROUTER / "SKILL.md"
BINDINGS = ROUTER / "profiles" / "bindings.md"
CODEX_PROFILE = ROUTER / "profiles" / "codex.md"
CLAUDE_PROFILE = ROUTER / "profiles" / "claude-code.md"
CODEX_ONBOARDING = ROUTER / "references" / "codex-project-onboarding.md"
CLAUDE_ONBOARDING = ROUTER / "references" / "claude-code-project-onboarding.md"

ROLES = ["light_worker", "standard_builder", "reviewer", "expert", "reanalyst"]
EFFORTS = {"low", "medium", "high", "xhigh", "max"}
MODEL_ID_RE = re.compile(
    r"gpt-\d|claude-[a-z]+-\d|\b(?:Sol|Terra|Luna|Astra|Opus|Sonnet|Haiku|Fable)\b"
)
PLACEHOLDER_RE = re.compile(r"^\{\{([a-z-]+)\.([a-z_]+)\.(model|effort)\}\}$")


def load_bindings() -> dict[str, dict[str, dict[str, str]]]:
    bindings: dict[str, dict[str, dict[str, str]]] = {}
    harness = None
    for line in BINDINGS.read_text(encoding="utf-8").splitlines():
        heading = re.fullmatch(r"## ([a-z][a-z-]*)", line)
        if heading:
            harness = heading.group(1)
            continue
        if line.startswith("## "):
            harness = None
            continue
        row = re.fullmatch(r"\| `([a-z_]+)` \| `([^`]+)` \| `([^`]+)` \|", line)
        if harness and row:
            role, model, effort = row.groups()
            bindings.setdefault(harness, {})[role] = {"model": model, "effort": effort}
    return bindings


def resolve(placeholder: str, harness: str, role: str, key: str) -> str:
    match = PLACEHOLDER_RE.fullmatch(placeholder)
    assert match, placeholder
    assert match.groups() == (harness, role, key), placeholder
    return load_bindings()[harness][role][key]


def test_bindings_table_is_complete_for_each_harness():
    bindings = load_bindings()

    assert set(bindings) == {"codex", "claude-code"}
    for harness, roles in bindings.items():
        assert sorted(roles) == sorted(ROLES), harness
        for role, value in roles.items():
            assert MODEL_ID_RE.search(value["model"]), (harness, role)
            assert value["effort"] in EFFORTS, (harness, role)


def test_model_ids_appear_only_in_bindings_table():
    models = {
        value["model"]
        for roles in load_bindings().values()
        for value in roles.values()
    }
    offenders = []
    for path in sorted(ROUTER.rglob("*")):
        if not path.is_file() or path == BINDINGS:
            continue
        text = path.read_text(encoding="utf-8")
        for line_number, line in enumerate(text.splitlines(), 1):
            if MODEL_ID_RE.search(line) or any(model in line for model in models):
                offenders.append(f"{path.relative_to(REPO_ROOT)}:{line_number}: {line}")

    assert offenders == []


def test_router_keeps_policy_and_harness_binding_separate():
    skill = SKILL.read_text(encoding="utf-8")

    for link in (
        "profiles/bindings.md",
        "profiles/codex.md",
        "profiles/claude-code.md",
    ):
        assert link in skill
    assert "Beads" not in skill
    for tier, role in (
        ("light", "light_worker"),
        ("standard", "standard_builder"),
        ("expert", "expert"),
    ):
        assert f"| `{tier}` | `{role}` |" in skill
    assert "| fresh review | `reviewer` |" in skill
    assert "| direction reanalysis | `reanalyst` |" in skill

    codex = CODEX_PROFILE.read_text(encoding="utf-8")
    claude = CLAUDE_PROFILE.read_text(encoding="utf-8")
    assert "read-only 主 session" in codex
    assert "profile=codex binding=standard_builder" in codex
    assert "profile=claude-code binding=standard_builder" in claude
    assert "不使用 fork" in claude
    assert "`permissionMode` 不能當唯讀證據" in claude
    for profile in (codex, claude):
        assert "bindings.md#三次方向誤判的主模型條件" in profile


def test_router_regression_cases_remain_explicit():
    skill = SKILL.read_text(encoding="utf-8")
    expected_routes = (
        "execute / light / low / direct / lead",
        "execute / standard / material / single_worker / lead",
        "execute / light / low / bounded_parallel / lead",
        "co_discover / frontier / direct",
        "explore_then_plan / frontier / material / direct",
        "explore_then_plan / expert / material / single_worker / lead",
        "explore_then_plan / frontier / critical / approval+fresh",
    )

    for route in expected_routes:
        assert route in skill


def test_router_requires_consent_before_creating_project_config():
    skill = SKILL.read_text(encoding="utf-8")
    assert "references/codex-project-onboarding.md" in skill
    assert "references/claude-code-project-onboarding.md" in skill
    assert "未取得使用者選擇前，不得建立或修改設定" in skill

    codex = CODEX_ONBOARDING.read_text(encoding="utf-8")
    claude = CLAUDE_ONBOARDING.read_text(encoding="utf-8")
    for onboarding in (codex, claude):
        for choice in ("建立建議設定", "只顯示建議", "暫不設定"):
            assert choice in onboarding
        assert "不要自動建立" in onboarding
        assert "保留抽象 tier" in onboarding

    assert "未信任的專案不會載入專案層設定" in codex
    for path in (
        ".codex/config.toml",
        ".codex/agents/light-worker.toml",
        ".codex/agents/standard-builder.toml",
        ".codex/agents/reviewer.toml",
        ".codex/agents/expert.toml",
        ".codex/agents/reanalyst.toml",
    ):
        assert path in codex
    for path in (
        ".claude/agents/light-worker.md",
        ".claude/agents/standard-builder.md",
        ".claude/agents/reviewer.md",
        ".claude/agents/expert.md",
        ".claude/agents/reanalyst.md",
    ):
        assert path in claude


def test_codex_onboarding_toml_examples_resolve_from_bindings():
    onboarding = CODEX_ONBOARDING.read_text(encoding="utf-8")
    toml_examples = re.findall(r"```toml\n(.*?)```", onboarding, flags=re.DOTALL)

    assert len(toml_examples) == 6
    config, *roles = (tomllib.loads(example) for example in toml_examples)

    assert config == {
        "agents": {"enabled": True, "max_concurrent_threads_per_session": 15}
    }
    assert [role["name"] for role in roles] == ROLES
    assert all("config_file" not in example for example in toml_examples)

    for role in roles:
        assert role["description"]
        assert role["developer_instructions"]
        name = role["name"]
        resolve(role["model"], "codex", name, "model")
        resolve(role["model_reasoning_effort"], "codex", name, "effort")
        if name in {"reviewer", "reanalyst"}:
            assert role["sandbox_mode"] == "read-only"
            assert role["approval_policy"] == "never"


def test_claude_code_onboarding_agents_resolve_from_bindings():
    onboarding = CLAUDE_ONBOARDING.read_text(encoding="utf-8")
    examples = re.findall(r"```markdown\n(.*?)```", onboarding, flags=re.DOTALL)

    assert len(examples) == len(ROLES)
    names = []
    for example in examples:
        assert example.startswith("---\n")
        frontmatter, body = example[4:].split("\n---\n", 1)
        fields = dict(line.split(": ", 1) for line in frontmatter.splitlines())
        name = fields["name"]
        names.append(name)

        assert ":" not in name and not name.startswith("-")
        assert fields["description"]
        assert body.strip()
        model = resolve(fields["model"].strip('"'), "claude-code", name, "model")
        effort = resolve(fields["effort"].strip('"'), "claude-code", name, "effort")
        assert model and effort in EFFORTS
        if name in {"reviewer", "reanalyst"}:
            assert fields["tools"] == "Read, Grep, Glob"
        else:
            assert "tools" not in fields

    assert names == ROLES
