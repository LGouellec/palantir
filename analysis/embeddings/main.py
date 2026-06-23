import os
from openai import AzureOpenAI

endpoint = "https://palantir-oai.openai.azure.com/"
model_name = "text-embedding-3-large"
deployment = "text-embedding-3-large-2"

api_version = "2024-02-01"
client = AzureOpenAI(
    api_version="2024-12-01-preview",
    azure_endpoint=endpoint,
    azure_deployment=deployment,
    api_key="XXXX"
)

response = client.embeddings.create(
    input=["first phrase","second phrase","third phrase"],
    model=deployment
)

for item in response.data:
    length = len(item.embedding)
    print(
        f"data[{item.index}]: length={length}, "
        f"[{item.embedding[0]}, {item.embedding[1]}, "
        f"..., {item.embedding[length-2]}, {item.embedding[length-1]}]"
    )
print(response.usage)