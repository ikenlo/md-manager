def test_list_all(client, auth):
    r = client.get("/api/dialogues", headers=auth)
    assert r.status_code == 200
    body = r.json()
    assert body["total"] == 3
    first = body["items"][0]
    assert first["client"]["name"] == "Олена Коваль"
    assert first["last_message"]["content"] == "15:30 підходить 🙌"
    assert first["tags"] == ["манікюр"]


def test_filters(client, auth):
    def names(**params):
        r = client.get("/api/dialogues", headers=auth, params=params)
        return [d["client"]["name"] for d in r.json()["items"]]

    assert names(status="new") == ["Марія Шевчук"]
    assert names(channel="facebook") == ["Анна Бондар"]
    assert names(tag="манікюр") == ["Олена Коваль"]
    assert names(q="masha") == ["Марія Шевчук"]
    assert names(status="lost") == []
    assert client.get("/api/dialogues", headers=auth, params={"status": "x"}).status_code == 422


def test_messages_and_post(client, auth):
    d = client.get("/api/dialogues", headers=auth, params={"status": "new"}).json()["items"][0]
    url = f"/api/dialogues/{d['uuid']}/messages"
    assert len(client.get(url, headers=auth).json()) == 1
    r = client.post(url, headers=auth, json={"content": "  Корекція — 350 грн  "})
    assert r.status_code == 201 and r.json()["sender_type"] == "human"
    msgs = client.get(url, headers=auth).json()
    assert [m["content"] for m in msgs][-1] == "Корекція — 350 грн"
    updated = client.get("/api/dialogues", headers=auth).json()["items"][0]
    assert updated["uuid"] == d["uuid"] and updated["status"] == "in_progress"


def test_post_validation_and_404(client, auth):
    d = client.get("/api/dialogues", headers=auth).json()["items"][0]
    url = f"/api/dialogues/{d['uuid']}/messages"
    assert client.post(url, headers=auth, json={"content": ""}).status_code == 400
    assert client.post(url, headers=auth, json={"text": "x" * 5001}).status_code == 422
    assert (
        client.post(url, headers=auth, json={"text": "x", "sender_type": "agent"}).status_code
        == 422
    )
    assert client.get("/api/dialogues/nope/messages", headers=auth).status_code == 404


def test_requires_auth(client):
    assert client.get("/api/dialogues").status_code == 401
