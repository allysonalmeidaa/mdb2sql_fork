from interface.app_flask_local_search import app


def test_admin_logs_collects_client_log():
    client = app.test_client()
    res = client.post("/client/log", json={"level": "error", "msg": "log-test"})
    assert res.status_code == 200
    data = res.get_json()
    assert data.get("ok") is True

    logs_res = client.get("/admin/logs")
    assert logs_res.status_code == 200
    logs_data = logs_res.get_json()
    assert logs_data.get("ok") is True
    logs = logs_data.get("logs") or []
    assert any("event=client_log" in entry.get("message", "") for entry in logs)
