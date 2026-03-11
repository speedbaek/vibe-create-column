import os
from dotenv import load_dotenv
from langchain_anthropic import ChatAnthropic

load_dotenv()

models_to_test = [
    "claude-3-7-sonnet-20250219",
    "claude-3-5-sonnet-20241022",
    "claude-3-5-sonnet-20240620",
    "claude-3-sonnet-20240229",
    "claude-3-opus-20240229",
    "claude-3-haiku-20240307",
    "claude-2.1"
]

print("Running API model test...")
with open("test_output.txt", "w", encoding="utf-8") as f:
    f.write("Testing available Anthropic models for the provided API key...\n")
    for model in models_to_test:
        try:
            llm = ChatAnthropic(model_name=model, temperature=0, max_tokens=10)
            res = llm.invoke("Hi")
            f.write(f"[SUCCESS] {model}\n")
            print(f"Tested {model}")
        except Exception as e:
            err_msg = str(e).split('\n')[0][:100]
            f.write(f"[FAILED] {model} - {err_msg}\n")
            print(f"Tested {model}")
print("Done.")
