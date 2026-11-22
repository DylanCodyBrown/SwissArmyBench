import swissarmybench as sab


def list_orders(status=None, pageToken=None):
    """Orders: GET /orders, through api_adapter (sab.run)."""
    answer = sab.run("Orders", "list_orders", {"status": status, "pageToken": pageToken})
    if not answer["ok"]:
        raise RuntimeError(answer["error"]["error"])
    return answer["records"]
