"""Knowledge-graph interface (D12/D31). Training deferred: status plumbing is
real, index/query raise until graphrag is wired. Stdlib only."""
import os

STATUS_NOT_INDEXED = "not_indexed"
STATUS_INDEXED = "indexed"


def get_status(agent_dir):
    """Honest status for the Crew tab. Never fakes an index."""
    idx = os.path.join(agent_dir, "graph_index")
    hb = os.path.join(agent_dir, "handbook")
    staged = sorted(f for f in os.listdir(hb) if f.endswith(".md")) \
        if os.path.isdir(hb) else []
    if os.path.isdir(idx):
        return {"state": STATUS_INDEXED, "path": idx, "staged": staged}
    return {"state": STATUS_NOT_INDEXED, "staged": staged,
            "reason": "GraphRAG training deferred (D31); handbook/ ready, "
                      "not indexed"}


def index_corpus(agent_dir):
    raise NotImplementedError("GraphRAG indexing deferred (D31)")


def query(agent_dir, question, top_k=5):
    raise NotImplementedError("GraphRAG query deferred (D31): no index yet")


def summarize(agent_dir):
    """Learning-result summary for the graph panel. Filled in after the
    first real graphrag index run. Contract: entities [{name, degree}],
    relations [{source, target}], communities [{title, size}]."""
    return {"entities": [], "relations": [], "communities": [],
            "note": "index reader wires up after the first graphrag index run"}
