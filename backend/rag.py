import math
import os
from typing import List, Dict, Any
from langchain_core.retrievers import BaseRetriever
from langchain_core.callbacks import CallbackManagerForRetrieverRun
from langchain_core.documents import Document
from langchain_core.embeddings import Embeddings
from langchain_community.vectorstores import FAISS

# Predefined AC energy-saving policies & manufacturer guidelines
AC_POLICIES = [
    Document(
        page_content="When the room is unoccupied, turn off the AC completely or set the target temperature to 28°C (82°F) in Eco mode. This prevents cooling empty spaces, saving up to 30-40% of energy.",
        metadata={"category": "occupancy", "trigger_type": "unoccupied", "priority": 1}
    ),
    Document(
        page_content="During peak electricity rate hours (high tariff), increase the cooling setpoint by 1.5°C to 2°C (3°F to 4°F) or set the AC to Eco Mode. Pre-cool the room by 1°C prior to peak hours to maintain comfort while avoiding peak-tariff power consumption.",
        metadata={"category": "tariff", "trigger_type": "peak_hours", "priority": 2}
    ),
    Document(
        page_content="If indoor humidity exceeds 60%, switch the AC mode to 'Dry'. Dry Mode runs the compressor in intervals to dehumidify the air. Removing moisture increases perceived comfort, allowing the thermostat to be set 1-2°C higher while consuming 15-20% less energy than standard Cool Mode.",
        metadata={"category": "humidity", "trigger_type": "high_humidity", "priority": 2}
    ),
    Document(
        page_content="When the outdoor temperature is moderate (below 24°C / 75°F), use Fan-Only Mode instead of Cool Mode. Running only the indoor fan consumes only 5-10% of the energy of running the compressor, while still providing air circulation and ventilation.",
        metadata={"category": "outdoor_temp", "trigger_type": "moderate_outdoor", "priority": 3}
    ),
    Document(
        page_content="For occupied rooms during standard hours, the optimal thermostat setpoint is 24°C to 25°C (75°F to 77°F). Every degree Celsius set below 24°C increases compressor power consumption by approximately 6-8%.",
        metadata={"category": "comfort", "trigger_type": "standard", "priority": 4}
    ),
    Document(
        page_content="During nighttime/sleep hours, implement a sleep curve: raise the temperature setpoint by 1°C after the first hour, and another 1°C after the second hour (max setting of 26°C / 79°F). Metabolism slows down during sleep, and this curve can reduce night energy usage by 15%.",
        metadata={"category": "time", "trigger_type": "sleep_hours", "priority": 3}
    )
]

class SimpleLocalEmbeddings(Embeddings):
    """
    A simple TF-IDF based embedding generator that runs locally and requires no external ML models.
    """
    vocab: List[str]
    vocab_idx: Dict[str, int]
    idf: Dict[str, float]

    def __init__(self, documents: List[str]):
        # Fit a simple TF-IDF vectorizer on the document vocabulary
        vocab = set()
        for doc in documents:
            for word in self._tokenize(doc):
                vocab.add(word)
        self.vocab = sorted(list(vocab))
        self.vocab_idx = {word: i for i, word in enumerate(self.vocab)}
        
        # Calculate IDF
        self.idf = {}
        num_docs = len(documents)
        for word in self.vocab:
            doc_count = sum(1 for doc in documents if word in self._tokenize(doc))
            self.idf[word] = math.log((1 + num_docs) / (1 + doc_count)) + 1.0

    def _tokenize(self, text: str) -> List[str]:
        return text.lower().replace(",", " ").replace(".", " ").replace("(", " ").replace(")", " ").split()

    def _embed(self, text: str) -> List[float]:
        tokens = self._tokenize(text)
        vector = [0.0] * len(self.vocab)
        if not tokens:
            if self.vocab:
                vector[0] = 1.0
            return vector
        # Compute TF
        tf = {}
        for token in tokens:
            tf[token] = tf.get(token, 0) + 1
        # Compute TF-IDF
        for token, count in tf.items():
            if token in self.vocab_idx:
                idx = self.vocab_idx[token]
                vector[idx] = (count / len(tokens)) * self.idf[token]
        # Normalize vector (L2 norm)
        norm = math.sqrt(sum(val ** 2 for val in vector))
        if norm > 0:
            vector = [val / norm for val in vector]
        return vector

    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        return [self._embed(text) for text in texts]

    def embed_query(self, text: str) -> List[float]:
        return self._embed(text)

class ACPolicyRetriever(BaseRetriever):
    """
    A LangChain Retriever that queries AC Energy saving policies using FAISS.
    - Online Mode: Uses OpenAIEmbeddings if an API key is present.
    - Offline Mode: Uses SimpleLocalEmbeddings (TF-IDF based) if no API key is present.
    """
    api_key: str = ""
    documents: List[Document] = AC_POLICIES
    _vector_store: Any = None

    def __init__(self, api_key: str = "", **kwargs):
        super().__init__(**kwargs)
        self.api_key = api_key or os.environ.get("OPENAI_API_KEY", "")
        
        # Initialize Embeddings
        if self.api_key:
            try:
                from langchain_openai import OpenAIEmbeddings
                embeddings = OpenAIEmbeddings(openai_api_key=self.api_key)
            except Exception:
                embeddings = SimpleLocalEmbeddings([doc.page_content for doc in self.documents])
        else:
            embeddings = SimpleLocalEmbeddings([doc.page_content for doc in self.documents])
            
        # Initialize FAISS Vector Store
        self._vector_store = FAISS.from_documents(self.documents, embeddings)

    def _get_relevant_documents(
        self, query: str, *, run_manager: CallbackManagerForRetrieverRun
    ) -> List[Document]:
        # Return top 3 relevant documents using FAISS
        return self._vector_store.similarity_search(query, k=3)

def get_policy_retriever(api_key: str = "") -> ACPolicyRetriever:
    """Factory function to get the policy retriever."""
    return ACPolicyRetriever(api_key=api_key)

if __name__ == "__main__":
    # Small test
    retriever = get_policy_retriever()
    test_query = "unoccupied peak hours high humidity outdoor 22C"
    results = retriever.invoke(test_query)
    print(f"Query: '{test_query}'")
    for i, doc in enumerate(results):
        print(f"\nResult {i+1} [Category: {doc.metadata['category']}]:")
        print(doc.page_content)
