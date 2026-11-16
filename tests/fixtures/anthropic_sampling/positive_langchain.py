from langchain_anthropic import ChatAnthropic

llm = ChatAnthropic(model="claude-sonnet-5-5", temperature=0.3)
llm.invoke("Hello")
