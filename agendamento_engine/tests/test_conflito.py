import requests
import threading

URL = "http://127.0.0.1:8000/appointments"

payload = {
    "professional_id": "dd6de1da-32e9-4632-870e-95d8a1e21cd7",
    "client_id": "f39eb397-f948-4b07-8784-04e31e67eeb8",
    "start_at": "2026-04-06T15:00:00",
    "services": [
        {"service_id": "bce9c392-430f-442c-8dc7-b6ee6e7014b7"}
    ]
}

def send_request(i):
    data = payload.copy()
    data["idempotency_key"] = f"test-{i}"

    response = requests.post(URL, json=data)
    print(f"Request {i}: {response.status_code} - {response.text}")

threads = []

for i in range(2):
    t = threading.Thread(target=send_request, args=(i,))
    threads.append(t)
    t.start()

for t in threads:
    t.join()