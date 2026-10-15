from openai import OpenAI

client = OpenAI()
FUNCS = [{"name": "get_weather", "parameters": {"type": "object", "properties": {}}}]


def old_style(q):
    # legacy function calling
    return client.chat.completions.create(model="gpt-4o-2024-08-06", messages=[{"role": "user", "content": q}],
                                          functions=FUNCS, function_call="auto")


def assistant():
    return client.beta.assistants.create(model="gpt-4o", name="Helper", instructions="Be brief.")


def completion(p):
    return client.completions.create(model="gpt-4o-mini", prompt=p, max_tokens=50)


def train():
    return client.fine_tuning.jobs.create(model="gpt-4o-mini-2024-07-18", training_file="file-abc")
