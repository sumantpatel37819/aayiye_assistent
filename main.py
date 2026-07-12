from langchain_ollama.llms import OllamaLLM
from langchain_core.prompts import ChatPromptTemplate

model = OllamaLLM(model="llama3.2")

template = """
You are a tour guider name as "Raju betiya" from bhabua.
you are an expert in anwering about the history culture and famous of a {location} from bihar.
you answer the question in a friendly way and tell them how to reach there and what are the best time to visit there.
user question: {question}
"""
prompt = ChatPromptTemplate.from_template(template)
chain = prompt | model

while True:
    print("------------------------------------")
    question = input("Enter your question: ")
    if question == "q":
        break
    
    result = chain.invoke({
        "location": "Bhabua",
        "question": question
    })
    #print in chunk by chunk
    for chunk in result:
        print(chunk, end="")
    print()