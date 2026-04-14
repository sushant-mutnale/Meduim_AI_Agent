import requests
from app.core.config import settings

class MediumPublisher:
    def __init__(self):
        self.api_token = settings.MEDIUM_API_TOKEN
        self.user_id = settings.MEDIUM_USER_ID
        self.base_url = "https://api.medium.com/v1"

    def publish(self, title: str, body: str, publish_status: str = "draft"):
        # publish_status can be 'public', 'draft', or 'unlisted'
        headers = {
            "Authorization": f"Bearer {self.api_token}",
            "Content-Type": "application/json",
            "Accept": "application/json",
            "Accept-Charset": "utf-8"
        }
        
        url = f"{self.base_url}/users/{self.user_id}/posts"
        
        payload = {
            "title": title,
            "contentFormat": "markdown",
            "content": body,
            "publishStatus": publish_status,
            "tags": ["Tech", "AI", "Machine Learning"],
        }
        
        response = requests.post(url, json=payload, headers=headers)
        if response.status_code in [200, 201]:
            return response.json()
        else:
            raise Exception(f"Medium API Error: {response.text}")
