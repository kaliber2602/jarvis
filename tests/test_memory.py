from __future__ import annotations

from pathlib import Path
import sys
import tempfile

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agent.memory.memory_service import MemoryItem, QdrantMemoryProvider, get_memory_service
from agent.tool_registry import ToolRegistry


def test_memory_storage_and_recall():
    with tempfile.TemporaryDirectory() as tmp_dir:
        memory = QdrantMemoryProvider(storage_path=tmp_dir)

        # 1. Store preferences & facts
        id1 = memory.store("User prefers dark mode in Visual Studio Code", category="preference")
        id2 = memory.store("Current active project is Jarvis Voice Assistant in Python", category="project")
        assert id1 != ""
        assert id2 != ""

        # 2. Vector Semantic Search
        results = memory.search("visual studio code dark theme", limit=2)
        assert len(results) >= 1
        assert any("dark mode" in r.text for r in results)

        project_res = memory.search("what project are we working on", limit=2)
        assert len(project_res) >= 1
        assert any("Jarvis Voice Assistant" in r.text for r in project_res)

        memory.close()


def test_memory_tool_registry():
    registry = ToolRegistry.get_instance()
    assert registry.get_tool("search_memory") is not None
    assert registry.get_tool("store_memory") is not None

    # Execute store_memory tool
    res_store = registry.execute("store_memory", text="Test memory item for tool execution", category="test")
    assert res_store.get("success") is True

    # Execute search_memory tool
    res_search = registry.execute("search_memory", query="tool execution test")
    assert res_search.get("success") is True
    assert res_search.get("count", 0) >= 1


if __name__ == "__main__":
    test_memory_storage_and_recall()
    test_memory_tool_registry()
    print("All Qdrant Long-Term Memory & Tool Registry tests passed successfully!")
