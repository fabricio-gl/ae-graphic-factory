import os
from pathlib import Path

from mcp.server import MCPServer

ROOT = Path(__file__).resolve().parent
PLUGIN = ROOT / "plugins" / "ae-graphic-factory"

mcp = MCPServer("AE Graphic Factory")


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


@mcp.tool()
def graphic_spec_builder_instructions() -> str:
    """
    Use this tool when the user wants to analyze a graphic reference,
    define a motion graphic, or create a GRAPHIC_SPEC for After Effects.

    Call this before generating JSX.
    """
    return read_text(
        PLUGIN
        / "skills"
        / "graphic-spec-builder"
        / "SKILL.md"
    )


@mcp.tool()
def ae_graphic_jsx_creator_instructions() -> str:
    """
    Use this tool after a GRAPHIC_SPEC exists and the user wants
    production-ready JSX for Adobe After Effects 24.x.
    """
    return read_text(
        PLUGIN
        / "skills"
        / "ae-graphic-jsx-creator"
        / "SKILL.md"
    )


@mcp.tool()
def ae_graphic_factory_overview() -> str:
    """
    Load the AE Graphic Factory workflow, defaults and operating rules.
    Use when the user invokes AE Graphic Factory without specifying a phase.
    """
    return read_text(PLUGIN / "README.md")


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "8000"))

    mcp.run(
        transport="streamable-http",
        host="0.0.0.0",
        port=port,
        streamable_http_path="/mcp",
        json_response=True,
        stateless_http=True,
    )
