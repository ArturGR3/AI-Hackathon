# creating a project that takes a pdf, extracts the text, translates it to english, stores it in a vector db
from pdf_text_extractor import extract_text_from_pdf
import instructor
from dotenv import load_dotenv, find_dotenv
from openai import OpenAI
from pydantic import BaseModel, Field
from typing import List, Optional, Union, Literal, Tuple, Any
from datetime import date, datetime, timedelta
from enum import Enum
import os 
from google_api import GoogleAPI
import json
from rich.console import Console
from rich.prompt import Confirm, Prompt
from rich.panel import Panel
from rich import print as rprint
from rich.table import Table
from rich.live import Live
from rich.layout import Layout
from rich.console import Group
from pdf_modifier import add_summary_page

# Initialize core services
load_dotenv(find_dotenv(usecwd=True))
client = instructor.from_openai(OpenAI())
google_api = GoogleAPI()
console = Console()

class Appointment(BaseModel):
    """Represents an appointment with date, location, and required documents."""
    date: datetime = Field(description="The date and time of the appointment")
    location: str = Field(description="The location of the appointment")
    required_documents: Optional[List[str]] = Field(description="List of documents to bring to the appointment")
    additional_notes: Optional[str] = Field(description="Any additional notes about the appointment")

class ReplyRequired(BaseModel):
    documents_to_send_in_original_language: List[str] = Field(description="List of documents that need to be sent back in the original language")
    documents_to_send_in_english: List[str] = Field(description="List of documents that need to be sent back in English")
    deadline: datetime = Field(description="Deadline for sending the documents")
    address_to_send_to: str = Field(description="Address to send the documents to")

class PaymentDetails(BaseModel):
    recipient: str = Field(description="Who to pay")
    amount: float = Field(description="Amount to pay")
    deadline: datetime = Field(description="Payment deadline")
    bank_details: dict = Field(description="Bank details for payment")
    reference_number: Optional[str] = Field(description="Payment reference number if any")

class RequiredAction(BaseModel):
    action_type: Literal['no_action', 'appointment', 'reply_required', 'payment_required']
    appointment: Optional[Appointment] = None
    reply: Optional[ReplyRequired] = None
    payment: Optional[PaymentDetails] = None

class GovernmentDocument(BaseModel):
    title_in_original_language: str = Field(description="The title of the document in the original language")
    title_in_english: str = Field(description="Up to 3 words that describe the document based on the action required")
    sender: Literal['Employment Agency', 'Tax', 'Health', 'Immigration', 'Other'] = Field(description=f"Correctly assign the sender of the document, if none of the options fit, use 'Other'")
    sent_date: date = Field(description="The date the document was sent")
    addressed_to: str = Field(description="The person or entity to whom the document is addressed, without any titles or prefixes like Herr, Frau, Dr., etc.")
    content_in_original_language: str = Field(description="The content of the document in the original language")
    content_in_english: str = Field(description="The content of the document translated to English")
    summary_in_english: str = Field(description="A summary of the document content in English")
    required_actions: List[RequiredAction] = Field(description="List of required actions for this document")
    
def create_document_analysis(document: str):
    """
    Analyzes a document using LLM and returns structured information with streaming.
    
    Args:
        document (str): The text content of the document to analyze
        
    Returns:
        iterator: Stream of GovernmentDocument partial objects
    """
    return client.chat.completions.create_partial(
        model="gpt-4o-mini",
        response_model=GovernmentDocument,
        messages=[{
            "role": "user", 
            "content": f"""
            You are a government document expert that is fluent in German bureaucracy.
            You are given a document in German or English.I
            You need to analyze the document and provide response in JSON format.
            
            Here is the document:
            {document}
            """
        }],
        stream=True,
        validation_context={"partial": True}  # Enable partial validation
    )

def serialize_dates(obj: Union[datetime, date]) -> str:
    """
    Serializes datetime/date objects to ISO format strings for JSON compatibility.
    
    Args:
        obj: DateTime or Date object to serialize
        
    Returns:
        str: ISO formatted date string
        
    Raises:
        TypeError: If object cannot be serialized
    """
    if isinstance(obj, (datetime, date)):
        return obj.isoformat()
    raise TypeError(f"Type {type(obj)} not serializable")
        
def display_document_info(doc_info: dict, live: Live) -> None:
    """
    Displays formatted document information in the console.
    
    Args:
        doc_info (dict): Document information dictionary
        live (Live): Rich Live display context
    """
    table = Table(show_header=False)
    table.add_column("Field", style="cyan")
    table.add_column("Value", style="green")
    
    # Add core document details with empty string fallbacks
    for field, key in [
        ("From", 'sender'),
        ("To", 'addressed_to'),
        ("Title", 'title_in_english')
    ]:
        value = doc_info.get(key, "Processing...")
        value = "Processing..." if value is None else str(value)
        table.add_row(field, value)
    
    summary = doc_info.get('summary_in_english', "Processing summary...")
    summary = "Processing summary..." if summary is None else str(summary)
    
    # Create a layout with both panels
    layout = Panel(
        Group(
            Panel(table, title="Document Information", border_style="blue"),
            Panel(summary, title="Summary", border_style="blue")
        )
    )
    
    live.update(layout)

def handle_actions(doc_info: dict, pdf_path: str) -> None:
    """
    Processes and creates calendar events for document actions.
    
    Args:
        doc_info (dict): Document information dictionary
        pdf_path (str): Path to the original PDF file
    """
    if not doc_info['required_actions']:
        console.print("[yellow]No actions required for this document.[/yellow]")
        return

    # Display actions table
    action_table = Table(title="Required Actions")
    action_table.add_column("Type", style="cyan")
    action_table.add_column("Details", style="green")

    for action in doc_info['required_actions']:
        action_type = action['action_type']
        details = ""
        
        if action_type == "appointment":
            details = f"Date: {action['appointment']['date']}\nLocation: {action['appointment']['location']}"
        elif action_type == "reply_required":
            details = f"Deadline: {action['reply']['deadline']}\nAddress: {action['reply']['address_to_send_to']}"
        elif action_type == "payment_required":
            details = f"Amount: {action['payment']['amount']}\nDeadline: {action['payment']['deadline']}"
        
        action_table.add_row(action_type.replace('_', ' ').title(), details)

    console.print(action_table)

    if Confirm.ask("Would you like to create calendar events for these actions?"):
        with console.status("[bold green]Creating calendar events..."):
            # Create folders and upload PDF
            addressed_to_folder_id = google_api.get_or_create_folder(doc_info['addressed_to'])
            sender_folder_id = google_api.get_or_create_folder(doc_info['sender'], addressed_to_folder_id)
            
            # Add summary page to PDF
            pdf_with_summary = add_summary_page(doc_info, pdf_path)
            
            # Create file name from document title and date
            file_name = f"{doc_info['sent_date']}_{doc_info['title_in_english'].replace(' ', '_')}.pdf"
            uploaded_file_id, stored_file_name = google_api.upload_pdf(
                sender_folder_id, 
                pdf_with_summary,  # Use the new PDF with summary
                custom_name=file_name
            )
            
            # Clean up the temporary file
            os.remove(pdf_with_summary)
            
            # Display storage information to user
            console.print(Panel(f"""
            [green]Document stored successfully![/green]
            Location: {doc_info['addressed_to']}/{doc_info['sender']}/{stored_file_name}
            Link: https://drive.google.com/file/d/{uploaded_file_id}/view
            """, title="Storage Information", border_style="green"))

            # Process actions and create calendar events
            for action in doc_info['required_actions']:
                if action['action_type'] == "appointment":
                    # Handle appointment date
                    appointment_date = action['appointment']['date']
                    if isinstance(appointment_date, str):
                        appointment_date = datetime.fromisoformat(appointment_date)
                    event_end_time = appointment_date + timedelta(hours=1)
                    
                    google_api.create_event(
                        summary=f"Appointment: {doc_info['title_in_english']}",
                        location=action['appointment']['location'],
                        description=f"""
                        Summary: {doc_info['summary_in_english']}
                        Required Documents: {action['appointment']['required_documents'] if action['appointment']['required_documents'] else 'None'}
                        Additional Notes: {action['appointment']['additional_notes'] if action['appointment']['additional_notes'] else 'None'}
                        Document Link: https://drive.google.com/file/d/{uploaded_file_id}/view
                        """,
                        start_time=appointment_date.isoformat(),
                        end_time=event_end_time.isoformat()
                    )

                elif action['action_type'] == "reply_required":
                    # Handle reply deadline
                    deadline_date = action['reply']['deadline']
                    if isinstance(deadline_date, str):
                        deadline_date = datetime.fromisoformat(deadline_date)
                    event_end_time = deadline_date + timedelta(hours=1)
                    
                    google_api.create_event(
                        summary=f"Deadline: Reply Required - {doc_info['title_in_english']}",
                        location=action['reply']['address_to_send_to'],
                        description=f"""
                        Summary: {doc_info['summary_in_english']}
                        Documents to send (Original): {action['reply']['documents_to_send_in_original_language']}
                        Documents to send (English): {action['reply']['documents_to_send_in_english']}
                        Address: {action['reply']['address_to_send_to']}
                        Document Link: https://drive.google.com/file/d/{uploaded_file_id}/view
                        """,
                        start_time=deadline_date.isoformat(),
                        end_time=event_end_time.isoformat()
                    )

                elif action['action_type'] == "payment_required":
                    # Handle payment deadline
                    payment_deadline = action['payment']['deadline']
                    if isinstance(payment_deadline, str):
                        payment_deadline = datetime.fromisoformat(payment_deadline)
                    event_end_time = payment_deadline + timedelta(hours=1)
                    
                    google_api.create_event(
                        summary=f"Deadline: Payment Required - {doc_info['title_in_english']}",
                        location="",
                        description=f"""
                        Summary: {doc_info['summary_in_english']}
                        Amount: {action['payment']['amount']}
                        Recipient: {action['payment']['recipient']}
                        Reference: {action['payment']['reference_number'] if action['payment']['reference_number'] else 'None'}
                        Bank Details: {action['payment']['bank_details']}
                        """,
                        start_time=payment_deadline.isoformat(),
                        end_time=event_end_time.isoformat()
                    )
        
        console.print("[bold green]Calendar events created successfully![/bold green]")

def main() -> None:
    """
    Main application entry point. Handles document processing workflow.
    """
    console.print("[bold blue]Document Analysis Tool[/bold blue]")
    
    pdf_path = Prompt.ask("Enter the path to your PDF file")
    
    try:
        document = extract_text_from_pdf(pdf_path)
        
        # Initialize the layout
        initial_table = Table(show_header=False)
        initial_table.add_column("Field", style="cyan")
        initial_table.add_column("Value", style="green")
        for field in ["From", "To", "Title"]:
            initial_table.add_row(field, "Processing...")
        
        initial_layout = Panel(
            Group(
                Panel(initial_table, title="Document Information", border_style="blue"),
                Panel("Processing summary...", title="Summary", border_style="blue")
            )
        )
        
        # Start Live display
        with Live(initial_layout, console=console, refresh_per_second=4) as live:
            # Stream the analysis
            for partial_resp in create_document_analysis(document):
                doc_info = partial_resp.model_dump()
                display_document_info(doc_info, live)
            
            # Save final response
            with open('resp.json', 'w') as file:
                json.dump(doc_info, file, default=serialize_dates, indent=2)
        
        handle_actions(doc_info, pdf_path)
        
    except Exception as e:
        console.print(f"[bold red]Error:[/bold red] {str(e)}")

if __name__ == "__main__":
    main()