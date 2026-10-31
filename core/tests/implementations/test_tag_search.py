"""Unit tests for TagAndDescriptionWordMatchStrategy."""

import pytest
from utcp.data.call_template import CallTemplate
from utcp.data.tool import Tool, JsonSchema
from utcp.data.utcp_manual import UtcpManual
from utcp.implementations.in_mem_tool_repository import InMemToolRepository
from utcp.implementations.tag_search import TagAndDescriptionWordMatchStrategy


def get_sample_tools():
    tpl = CallTemplate(name="test_manual", call_template_type="test")
    return [
        Tool(
            name="add_numbers",
            description="Add two numbers together in arithmetic",
            inputs=JsonSchema(type="object"),
            outputs=JsonSchema(type="object"),
            tool_call_template=tpl,
            tags=["math", "addition", "calculator"],
        ),
        Tool(
            name="subtract_numbers",
            description="Subtract two numbers in arithmetic",
            inputs=JsonSchema(type="object"),
            outputs=JsonSchema(type="object"),
            tool_call_template=tpl,
            tags=["math", "subtraction", "calculator"],
        ),
        Tool(
            name="send_email",
            description="Send an email to a recipient",
            inputs=JsonSchema(type="object"),
            outputs=JsonSchema(type="object"),
            tool_call_template=tpl,
            tags=["communication", "email"],
        ),
    ]


async def create_populated_repo():
    tools = get_sample_tools()
    repo = InMemToolRepository()
    tpl = CallTemplate(name="test_manual", call_template_type="test")
    manual = UtcpManual(tools=tools)
    await repo.save_manual(tpl, manual)
    return repo, tools


@pytest.mark.anyio
async def test_search_tools_limit_zero_returns_all_tools():
    """Verify limit=0 returns all matching tools without slicing to empty."""
    repo, tools = await create_populated_repo()
    strategy = TagAndDescriptionWordMatchStrategy()
    results = await strategy.search_tools(repo, "math", limit=0)
    assert len(results) == len(tools)


@pytest.mark.anyio
async def test_search_tools_positive_limit_respected():
    """Verify limit > 0 returns at most `limit` results."""
    repo, _ = await create_populated_repo()
    strategy = TagAndDescriptionWordMatchStrategy()
    results = await strategy.search_tools(repo, "math", limit=1)
    assert len(results) == 1
    assert results[0].name in ("add_numbers", "subtract_numbers")


@pytest.mark.anyio
async def test_search_tools_negative_limit_raises_error():
    """Verify negative limit raises ValueError."""
    repo, _ = await create_populated_repo()
    strategy = TagAndDescriptionWordMatchStrategy()
    with pytest.raises(ValueError, match="limit must be non-negative"):
        await strategy.search_tools(repo, "math", limit=-1)


@pytest.mark.anyio
async def test_search_tools_tag_and_description_matching():
    """Verify tools with matching tags rank highest."""
    repo, _ = await create_populated_repo()
    strategy = TagAndDescriptionWordMatchStrategy()
    results = await strategy.search_tools(repo, "email", limit=10)
    assert len(results) > 0
    assert results[0].name == "send_email"


@pytest.mark.anyio
async def test_search_tools_any_of_tags_required():
    """Verify any_of_tags_required filters out non-matching tools."""
    repo, _ = await create_populated_repo()
    strategy = TagAndDescriptionWordMatchStrategy()
    results = await strategy.search_tools(
        repo,
        "numbers",
        limit=0,
        any_of_tags_required=["addition"],
    )
    assert len(results) == 1
    assert results[0].name == "add_numbers"
