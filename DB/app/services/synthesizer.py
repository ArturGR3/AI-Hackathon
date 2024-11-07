from typing import List, Optional, Literal
import pandas as pd
import json
from pydantic import BaseModel, Field
from services.llm_factory import LLMFactory
from datetime import datetime

class SynthesizedResponse(BaseModel):
    thought_process: List[str] = Field(description="List of thoughts that the AI assistant had while synthesizing the answer")
    answer: str = Field(description="The synthesized answer to the user's question")
    enough_context: bool = Field(description="Whether the assistant has enough context to answer the question")

class TimeFilter(BaseModel):
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None

class UserQuestionPreprocessing(BaseModel):
    question: str = Field(description="The user's question")
    sender: Optional[Literal['Employment Agency', 'Tax', 'Health', 'Immigration', 'Other']] = Field(description="The sender of the document")
    addressed_to: Optional[Literal['Artur Grygorian', 'Nune Grygorian']] = Field(description="The recipient of the document")
    time_filter: Optional[TimeFilter] = Field(description="The time filter for the search")

class Synthesizer:
    SYSTEM_PROMPT = """
    # Role and Purpose
    You are an AI assistant that helps users answer their questions about the documents they receive from the government. 
    Your task is to synthesize a coherent and helpful answer based on the given question and relevant context retrieved from a knowledge database.

    # Guidelines:
    1. Provide a reference to the document that contains the answer. Specify the title and the date of the document.
    2. Properly structure your answer, e.g. use bullet points if needed, and use markdown formatting.
    2. Provide a clear and concise answer to the question.
    3. Use only the information from the relevant context to support your answer.
    4. The context is retrieved based on cosine similarity, so some information might be missing or irrelevant.
    5. Be transparent when there is insufficient information to fully answer the question.
    6. Do not make up or infer information not present in the provided context.
    7. If you cannot answer the question based on the given context, clearly state that.
    8. Maintain a helpful and professional tone appropriate for customer service.
    9. Adhere strictly to company guidelines and policies by using only the provided knowledge base.
    
    Review the question from the user:
    """

    @staticmethod
    def generate_response(question: str, context: pd.DataFrame) -> SynthesizedResponse:
        """Generates a synthesized response based on the question and context.

        Args:
            question: The user's question.
            context: The relevant context retrieved from the knowledge base.

        Returns:
            A SynthesizedResponse containing thought process and answer.
        """
        context_str = Synthesizer.dataframe_to_json(
            context, 
            columns_to_keep=[
                "title_in_english",
                "title_in_original_language",
                "sender",
                "sent_date",
                "addressed_to",
                "summary_in_english",
                "required_actions"
            ]
        )

        messages = [
            {"role": "system", "content": Synthesizer.SYSTEM_PROMPT},
            {"role": "user", "content": f"# User question:\n{question}"},
            {
                "role": "assistant",
                "content": f"# Retrieved information:\n{context_str}",
            },
        ]

        llm = LLMFactory("openai")
        return llm.create_completion(
            response_model=SynthesizedResponse,
            messages=messages,
        )

    @staticmethod
    def dataframe_to_json(
        context: pd.DataFrame,
        columns_to_keep: List[str],
    ) -> str:
        """
        Convert the context DataFrame to a JSON string.

        Args:
            context (pd.DataFrame): The context DataFrame.
            columns_to_keep (List[str]): The columns to include in the output.

        Returns:
            str: A JSON string representation of the selected columns.
        """
        # Extract fields from metadata column and combine with main DataFrame
        result_records = []
        for _, row in context.iterrows():
            metadata = row['metadata']
            record = {
                'content': row['contents'],  # This is the main content field
                **{k: metadata.get(k) for k in columns_to_keep if k in metadata}
            }
            result_records.append(record)
            
        return json.dumps(result_records, indent=2, default=str)
