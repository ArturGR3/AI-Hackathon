from typing import Optional
from datetime import datetime, timedelta
from timescale_vector import client
from services.synthesizer import UserQuestionPreprocessing, Synthesizer
from services.llm_factory import LLMFactory
from database.vector_store import VectorStore

class QueryProcessor:
    def __init__(self):
        self.vector_store = VectorStore()
        self.llm = LLMFactory("openai")
        self.last_preprocessed_query = None

    def process_query(self, user_question: str) -> dict:
        """
        Process a user query through the following steps:
        1. Preprocess the question to extract metadata
        2. Build predicates based on extracted metadata
        3. Perform filtered vector search
        4. Synthesize final response
        
        Args:
            user_question: The raw question from the user
            
        Returns:
            dict: The final response including answer, thought process, and preprocessing details
        """
        # Step 1: Preprocess the question
        preprocessed = self._preprocess_question(user_question)
        self.last_preprocessed_query = preprocessed
        
        # Step 2: Build predicates based on extracted metadata
        predicates = self._build_predicates(preprocessed)
        
        # Step 3: Perform filtered vector search
        time_range = None
        if preprocessed.time_filter:
            time_range = (
                preprocessed.time_filter.start_date,
                preprocessed.time_filter.end_date
            )
        
        search_results = self.vector_store.search(
            user_question,
            limit=3,
            predicates=predicates,
            time_range=time_range
        )
        
        # Step 4: Synthesize final response
        response = Synthesizer.generate_response(
            question=user_question,
            context=search_results
        )
        
        return {
            "response": response,
            "preprocessing": preprocessed
        }

    def _preprocess_question(self, question: str) -> UserQuestionPreprocessing:
        """
        Preprocess the user question to extract metadata using LLM.
        """
        return self.llm.create_completion(
            response_model=UserQuestionPreprocessing,
            messages=[
                {
                    "role": "system",
                    "content": f"You are a query generator based on the user's question. The current date is {datetime.now().strftime('%Y-%m-%d')}"
                },
                {"role": "user", "content": f"# User question: {question}"},
            ],
        )

    def _build_predicates(self, preprocessed: UserQuestionPreprocessing) -> Optional[client.Predicates]:
        """
        Build predicates based on the preprocessed question metadata.
        """
        predicates_list = []

        # Add sender predicate if specified
        if preprocessed.sender:
            predicates_list.append(
                client.Predicates("category", "==", preprocessed.sender)
            )

        # Add addressed_to predicate if specified
        if preprocessed.addressed_to:
            predicates_list.append(
                client.Predicates("addressed_to", "==", preprocessed.addressed_to)
            )

        # Combine all predicates with OR operation like in similarity_search.py
        final_predicate = None
        for predicate in predicates_list:
            if final_predicate is None:
                final_predicate = predicate
            else:
                final_predicate = final_predicate | predicate  # Using OR instead of AND

        return final_predicate

# Example usage:
if __name__ == "__main__":
    processor = QueryProcessor()
    
    # Example queries
    queries = [
        "What are the last week's documents for Artur Grygorian?",
        # "Show me all Immigration documents addressed to Nune Grygorian from last month",
        # "What documents did I receive from the Tax office this year?"
    ]
    
    for query in queries:
        print(f"\nProcessing query: {query}")
        result = processor.process_query(query)
        
        print("\nPreprocessing details:")
        print(f"Time filter: {result['preprocessing'].time_filter}")
        print(f"Sender: {result['preprocessing'].sender}")
        print(f"Addressed to: {result['preprocessing'].addressed_to}")
        
        print("\nAnswer:", result['response'].answer)
        print("\nThought process:")
        for thought in result['response'].thought_process:
            print(f"- {thought}")
        print(f"Enough context: {result['response'].enough_context}")