import os
import json
from langchain_core.documents import Document
from langchain_anthropic import ChatAnthropic
# Note: We will use a lightweight local embedding model instead of OpenAI.
# sentence-transformers is great for Korean text
from langchain_community.vectorstores import Chroma
from langchain_cohere import CohereEmbeddings
from langchain_text_splitters import RecursiveCharacterTextSplitter

DB_DIR = "./chroma_db"

def load_texts(json_path):
    with open(json_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    documents = []
    for item in data:
        # We prepend title and date to give context to every chunk
        content = f"제목: {item['title']}\n작성일: {item['date']}\n\n{item['content']}"
        documents.append(Document(page_content=content, metadata={"title": item['title'], "date": item['date']}))
    return documents

def build_vector_db(persona_id, json_path):
    print(f"Loading texts from {json_path}...")
    documents = load_texts(json_path)
    
    # Split text into manageable chunks
    print("Splitting texts into chunks...")
    text_splitter = RecursiveCharacterTextSplitter(
        chunk_size=1000,
        chunk_overlap=200,
        separators=["\n\n", "\n", " ", ""]
    )
    splits = text_splitter.split_documents(documents)
    print(f"Created {len(splits)} chunks from {len(documents)} documents.")
    
    # Initialize embeddings (Cohere multilingual is great for Korean text and requires no heavy local setup)
    print("Initializing Cohere embedding model...")
    
    # Needs COHERE_API_KEY environment variable
    if "COHERE_API_KEY" not in os.environ:
        raise ValueError("COHERE_API_KEY is missing from environment variables.")
        
    embeddings = CohereEmbeddings(model="embed-multilingual-v3.0")
    
    # Create and persist vector database
    persist_directory = os.path.join(DB_DIR, persona_id)
    print(f"Building Vector DB at {persist_directory}...")
    
    vectorstore = Chroma.from_documents(
        documents=splits, 
        embedding=embeddings,
        persist_directory=persist_directory
    )
    print("Vector DB successfully built!")
    return vectorstore

if __name__ == "__main__":
    # Test building the DB if the sample exists
    if os.path.exists("data/all_texts_compiled.json"):
        build_vector_db("yun_ung_chae", "data/all_texts_compiled.json")
    else:
        print("data/all_texts_compiled.json not found. Run extractor.py first.")
