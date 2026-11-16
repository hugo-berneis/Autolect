"""Template and Course storage tests."""
from __future__ import annotations


def test_template_crud(client):
    r = client.post(
        "/api/templates",
        json={"name": "Adaptive", "content": "default prompt", "is_default": True},
    )
    assert r.status_code == 201
    tpl = r.json()
    assert tpl["is_default"] is True

    assert len(client.get("/api/templates").json()) == 1
    assert client.get(f"/api/templates/{tpl['id']}").json()["name"] == "Adaptive"

    r = client.put(
        f"/api/templates/{tpl['id']}",
        json={"name": "Adaptive v2", "content": "new", "is_default": False},
    )
    assert r.status_code == 200 and r.json()["name"] == "Adaptive v2"

    assert client.delete(f"/api/templates/{tpl['id']}").status_code == 204
    assert client.get(f"/api/templates/{tpl['id']}").status_code == 404


def test_course_vocab_upsert_remembered(client):
    # create
    r = client.put("/api/courses", json={"name": "CS101", "vocabulary": "BFS, DFS, DAG"})
    assert r.status_code == 200
    assert r.json()["vocabulary"] == "BFS, DFS, DAG"

    # update same course name -> upsert, not duplicate
    r = client.put("/api/courses", json={"name": "CS101", "vocabulary": "BFS, DFS, DAG, MST"})
    assert r.status_code == 200
    assert "MST" in r.json()["vocabulary"]
    assert len(client.get("/api/courses").json()) == 1

    assert client.get("/api/courses/CS101").json()["vocabulary"].endswith("MST")
    assert client.get("/api/courses/NOPE").status_code == 404
