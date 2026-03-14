import requests
import json
import os
import time

# read from .secret/openrouter_api_key_stepfun_3_5_flash
with open(".secret/openrouter_api_key_stepfun_3_5_flash", "r", encoding="utf-8") as f:
    OPENROUTER_API_KEY_STEPFUN_3_5_FLASH = f.read().strip()


class OpenRouterClient:
    def __init__(self, api_key=OPENROUTER_API_KEY_STEPFUN_3_5_FLASH, model="stepfun/step-3.5-flash:free"):
        self.api_key = api_key or os.environ.get("OPENROUTER_API_KEY")
        self.model = model
        self.url = "https://openrouter.ai/api/v1/chat/completions"

    def chat(self, messages, reasoning=True, temperature=0.7):
        if not self.api_key:
            raise ValueError("OPENROUTER_API_KEY is not set.")

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        
        data = {
            "model": self.model,
            "messages": messages,
            "reasoning": {"enabled": reasoning},
            "temperature": temperature
        }

        response = requests.post(
            url=self.url,
            headers=headers,
            data=json.dumps(data),
            timeout=120 # OpenRouter models with reasoning can take longer
        )

        if response.status_code != 200:
            raise Exception(f"OpenRouter API error: {response.status_code} - {response.text}")

        res_json = response.json()
        return res_json['choices'][0]['message']

    def call_json(self, prompt, reasoning=True):
        """
        Similar to the original call_gemini_json, returns a dict.
        """
        messages = [{"role": "user", "content": prompt}]
        try:
            message = self.chat(messages, reasoning=reasoning)
            content = message.get("content", "")
            
            # Find JSON in the response
            import re
            match = re.search(r'\{.*\}', content, re.DOTALL)
            if match:
                return json.loads(match.group(0))
            else:
                return {"error": f"No JSON found in response. Content: {content[:100]}..."}
        except Exception as e:
            return {"error": str(e)}

    def call_text(self, prompt, reasoning=True):
        """
        Similar to the original call_gemini_text, returns a string.
        """
        messages = [{"role": "user", "content": prompt}]
        try:
            message = self.chat(messages, reasoning=reasoning)
            return message.get("content", "").strip()
        except:
            return ""

# Example usage for testing (uncomment to test locally)
# if __name__ == "__main__":
#     client = OpenRouterClient()
#     resp = client.call_json("Give me a JSON with { 'test': 'hello' }")
#     print(resp)
