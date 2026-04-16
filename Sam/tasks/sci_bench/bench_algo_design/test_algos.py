"""Tests for BFS and Dijkstra implementations.

Expects:
  - bfs.py     with ``bfs(graph, start, end) -> (path, distance)``
  - dijkstra.py with ``dijkstra(graph, start, end) -> (path, distance)``

graph format:  dict[str, list[tuple[str, int]]]
  e.g. {"A": [("B", 1), ("C", 1)], ...}
For unweighted graphs every weight is 1.
"""

import json
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(__file__))

from bfs import bfs
from dijkstra import dijkstra

FIXTURES_DIR = os.path.dirname(__file__)


def _load_graph():
    """Load graph.json and return an adjacency-list dict with weight 1."""
    with open(os.path.join(FIXTURES_DIR, "graph.json")) as f:
        raw = json.load(f)
    adj = {n: [] for n in raw["nodes"]}
    for u, v in raw["edges"]:
        adj[u].append((v, 1))
        adj[v].append((u, 1))
    return adj, raw["start"], raw["end"]


@pytest.fixture
def graph_data():
    return _load_graph()


# ---- BFS tests ----

def test_bfs_shortest_path(graph_data):
    adj, start, end = graph_data
    path, dist = bfs(adj, start, end)
    assert path[0] == start
    assert path[-1] == end
    # A -> D -> G -> H  (length 3) is a valid shortest path
    assert dist == 3


def test_bfs_correct_distance(graph_data):
    adj, _, _ = graph_data
    _, dist = bfs(adj, "A", "G")
    assert dist == 2  # A->D->G or A->B->D->G? A-D direct edge exists, so A->D->G = 2


def test_bfs_disconnected():
    adj = {"X": [], "Y": []}
    path, dist = bfs(adj, "X", "Y")
    assert path == []
    assert dist == -1


# ---- Dijkstra tests ----

def test_dijkstra_shortest_path(graph_data):
    adj, start, end = graph_data
    path, dist = dijkstra(adj, start, end)
    assert path[0] == start
    assert path[-1] == end
    assert dist == 3


def test_dijkstra_self_loop():
    adj = {"A": [("A", 0), ("B", 1)], "B": [("A", 1)]}
    path, dist = dijkstra(adj, "A", "B")
    assert path == ["A", "B"]
    assert dist == 1


def test_bfs_dijkstra_agree(graph_data):
    """On an unweighted graph BFS and Dijkstra must give the same distance."""
    adj, start, end = graph_data
    _, d_bfs = bfs(adj, start, end)
    _, d_dij = dijkstra(adj, start, end)
    assert d_bfs == d_dij
