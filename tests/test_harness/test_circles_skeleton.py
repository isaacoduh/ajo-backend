import httpx


async def test_circles_ping(app_client: httpx.AsyncClient) -> None:
    response = await app_client.get("/circles/ping")

    assert response.status_code == 200
    assert response.json() == {"module": "circles", "status": "ok"}
