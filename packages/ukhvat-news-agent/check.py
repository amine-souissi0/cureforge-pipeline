import requests
import json

r = requests.get('https://api.telegram.org/bot8638520456:AAEKfd3q-LqBXMQbVa9XhUnIbKkZLgU1hdo/getUpdates?limit=10')
print(json.dumps(r.json(), indent=2))