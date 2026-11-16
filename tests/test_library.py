"""Library API tests."""
from __future__ import annotations

from app.models import TranscriptSegment


def _create(client, title="Intro to Algorithms", course="CS101", **kw):
    body = {"title": title, "course": course, **kw}
    r = client.post("/api/lectures", json=body)
    assert r.status_code == 201, r.text
    return r.json()


def test_create_and_get(client):
    lec = _create(client)
    assert lec["id"] > 0
    assert lec["title"] == "Intro to Algorithms"
    assert lec["course"] == "CS101"
    assert lec["status"] == "recording"
    assert lec["user_id"] == "default"

    r = client.get(f"/api/lectures/{lec['id']}")
    assert r.status_code == 200
    assert r.json()["id"] == lec["id"]


def test_list_orders_newest_first(client):
    a = _create(client, title="First")
    b = _create(client, title="Second")
    ids = [x["id"] for x in client.get("/api/lectures").json()]
    assert ids[0] == b["id"] and ids[1] == a["id"]


def test_rename_and_retag(client):
    lec = _create(client)
    r = client.patch(f"/api/lectures/{lec['id']}/rename", json={"title": "Renamed"})
    assert r.status_code == 200 and r.json()["title"] == "Renamed"

    r = client.patch(f"/api/lectures/{lec['id']}/retag", json={"course": "CS202"})
    assert r.status_code == 200 and r.json()["course"] == "CS202"


def test_search_by_title_course_and_transcript(client, session):
    lec_a = _create(client, title="Graph Theory", course="MATH")
    lec_b = _create(client, title="Linear Algebra", course="MATH")

    # Add a transcript segment to lec_b only.
    session.add(
        TranscriptSegment(
            lecture_id=lec_b["id"], seq=0, start_sec=0, end_sec=5,
            text="eigenvalues and eigenvectors",
        )
    )
    session.commit()

    # Title match
    ids = [x["id"] for x in client.get("/api/lectures", params={"q": "Graph"}).json()]
    assert ids == [lec_a["id"]]

    # Course match returns both (newest first)
    ids = [x["id"] for x in client.get("/api/lectures", params={"q": "MATH"}).json()]
    assert set(ids) == {lec_a["id"], lec_b["id"]}

    # Full-text transcript match returns only lec_b
    ids = [x["id"] for x in client.get("/api/lectures", params={"q": "eigen"}).json()]
    assert ids == [lec_b["id"]]

    # Exact course filter
    ids = [x["id"] for x in client.get("/api/lectures", params={"course": "MATH"}).json()]
    assert set(ids) == {lec_a["id"], lec_b["id"]}


def test_delete_cascades_segments(client, session):
    lec = _create(client)
    session.add(
        TranscriptSegment(lecture_id=lec["id"], seq=0, start_sec=0, end_sec=1, text="hi")
    )
    session.commit()

    r = client.delete(f"/api/lectures/{lec['id']}")
    assert r.status_code == 204
    assert client.get(f"/api/lectures/{lec['id']}").status_code == 404

    remaining = session.query(TranscriptSegment).filter_by(lecture_id=lec["id"]).count()
    assert remaining == 0


def test_download_notes_and_transcript(client, session):
    lec = _create(client, title="Downloads 101")
    # seed notes + transcript
    from app.models import Lecture

    obj = session.get(Lecture, lec["id"])
    obj.notes_markdown = "# Notes\n- point one"
    session.add(obj)
    session.add(
        TranscriptSegment(
            lecture_id=lec["id"], seq=0, start_sec=65, end_sec=70, text="hello world"
        )
    )
    session.commit()

    r = client.get(f"/api/lectures/{lec['id']}/notes.md")
    assert r.status_code == 200
    assert "# Notes" in r.text
    assert "attachment" in r.headers["content-disposition"]
    assert r.headers["content-disposition"].endswith('.md"')

    r = client.get(f"/api/lectures/{lec['id']}/transcript")
    assert r.status_code == 200
    assert "[01:05] hello world" in r.text


def test_not_found_paths(client):
    assert client.get("/api/lectures/999").status_code == 404
    assert client.patch("/api/lectures/999/rename", json={"title": "x"}).status_code == 404
    assert client.delete("/api/lectures/999").status_code == 404


def test_pipeline_stubs_return_501(client):
    lec = _create(client)
    assert client.post(f"/api/lectures/{lec['id']}/retranscribe").status_code == 501
    assert client.post(f"/api/lectures/{lec['id']}/regenerate").status_code == 501
