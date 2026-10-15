from langchain_openai import ChatOpenAI

llm = ChatOpenAI(model="gpt-4o", max_tokens=100, temperature=0.2)
