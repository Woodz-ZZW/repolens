import os
from openai  import OpenAI
from dotenv  import load_dotenv
from typing  import List, Dict
from pathlib import Path
from tools   import read_readme

load_dotenv()

class agentLLM:
    def __init__(self, model: str = None, apiKey: str = None, baseUrl: str = None, timeout: int = None):
        self.model = model or os.getenv("LLM_MODEL_ID")
        apiKey = apiKey or os.getenv("LLM_API_KEY")
        baseUrl = baseUrl or os.getenv("LLM_BASE_URL")
        timeout = timeout or int(os.getenv("LLM_TIMEOUT", 60))

        if not all([self.model, baseUrl, apiKey]):
            raise ValueError("Model ID, API key, and service address must be provided or defined in the .env file.")

        self.client = OpenAI(api_key=apiKey, base_url=baseUrl, timeout=timeout)
        self.reasoning_effort = os.getenv("LLM_REASONING_EFFORT")

    def think(self,messages: List[Dict[str,str]], temperature: float = 1) ->str | None:
        print(f"正在调用{self.model}模型")
        try:
            response = self.client.chat.completions.create(
                model       = self.model,
                messages    = messages,
                temperature = temperature,
                stream = True,
            )

            print("大模型响应成功")
            collected_content = []
            for chunk in response:
                if not chunk.choices:
                    continue
                content = chunk.choices[0].delta.content or ""
                print(content, end="", flush=True)
                collected_content.append(content)
            print()
            return "".join(collected_content)

        except Exception as e:
            print(f"调用LLM API时发生报错: {e}")
            return None

if __name__ == '__main__':
    try:
        llmClient = agentLLM()

        repo_dir    = str(Path(__file__).resolve().parent)
        readme_text = read_readme(repo_dir)
        
        messages = [
            {
                "role": "system", 
                "content":( 
                    "你是一个仓库阅读助手，只根据提供的 README 回答。"
                    "区分已实现功能和计划功能，未说明的信息不要猜测"
                ),
            },
            {
                "role": "user",
                "content": (
                    "请介绍这个项目的用途、已实现功能和计划功能。\n\n"
                    f"README 内容：\n{readme_text}"
                ),
            },
        ]

        print("---调用LLM---")
        responseText = llmClient.think(messages)
        if responseText:
            print("\n\n---完成模型响应---")
            print(responseText)

    except ValueError as e:
        print(e)