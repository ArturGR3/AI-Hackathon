# creating a project that takes a pdf, extracts the text, translates it to english, stores it in a vector db
from pdf_text_extractor import extract_text_from_pdf
import instructor
from dotenv import load_dotenv, find_dotenv
from openai import OpenAI
from pydantic import BaseModel, Field
from typing import List, Optional, Union, Literal
from datetime import date, datetime, timedelta
from enum import Enum
import os 
from google_api import GoogleAPI
import json
load_dotenv(find_dotenv(usecwd=True))

client = instructor.from_openai(OpenAI())

# Initialize Google API
google_api = GoogleAPI()

class Appointment(BaseModel):
    date: datetime = Field(description="The date and time of the appointment")
    location: str = Field(description="The location of the appointment")
    required_documents: Optional[List[str]] = Field(default=None, description="List of documents to bring to the appointment")
    additional_notes: Optional[str] = Field(default=None, description="Any additional notes about the appointment")

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
    reference_number: Optional[str] = Field(default=None, description="Payment reference number if any")

class RequiredAction(BaseModel):
    action_type: Literal['no_action', 'appointment', 'reply_required', 'payment_required']
    appointment: Optional[Appointment] = None
    reply: Optional[ReplyRequired] = None
    payment: Optional[PaymentDetails] = None

# Things to add:
# - sender could be based on the list of potential senders or 'other'
# - add a calendar event
# - add a google drive folder

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

# load the document
pdf_path = "/home/artur/github/personal/OCR_learning/scans/document.pdf"
document = extract_text_from_pdf(pdf_path)
    
def create_document_analysis(document: str):
    resp, completion = client.chat.completions.create_with_completion(
        model="gpt-4o-mini",
        response_model=GovernmentDocument,
        messages=[{"role": "user", "content": f"""
               You are a government document expert that is fluent in German bureaucracy.
               You are given a document in German or English.
               You need to analyze the document and provide responce in JSON format.
               Here is the document:
               {document}
               """}],
    )
    return resp, completion

resp, completion = create_document_analysis(document)

# Function to convert date objects to strings
def serialize_dates(obj):
    if isinstance(obj, (datetime, date)):
        return obj.isoformat()  # Convert to ISO format string
    raise TypeError(f"Type {type(obj)} not serializable")

# save resp in a json file
with open('resp.json', 'w') as file:
    json.dump(resp.model_dump(), file, default=serialize_dates, indent=2)  # Use the custom serializer

# Load the JSON file
with open('resp.json', 'r') as file:
    resp = json.load(file)

# print(resp.model_dump_json(indent=4))


# # create a folder for a document with the name of the resp.addressed_to
# os.makedirs(f"{resp.addressed_to}", exist_ok=True)
# # create a folder for a document with the name of the resp.sender inside the addressed_to folder
# os.makedirs(f"{resp.addressed_to}/{resp.sender}", exist_ok=True)
# # move original pdf to the addressed_to/sender folder with the name of the resp.title_in_english
# os.rename(pdf_path, f"{resp.addressed_to}/{resp.sender}/{resp.title_in_english}.pdf")

# Create or get subfolder for sender
addressed_to_folder_id = google_api.get_or_create_folder(resp['addressed_to'])
sender_folder_id = google_api.get_or_create_folder(resp['sender'], addressed_to_folder_id)

# Upload the PDF to Google Drive and store the file ID
uploaded_file_id = google_api.upload_pdf(sender_folder_id, pdf_path)
file_link = f"https://drive.google.com/file/d/{uploaded_file_id}/view"

# Process actions and create calendar events
for action in resp['required_actions']:
    if action['action_type'] == "appointment":
        # Parse the date string back to datetime
        appointment_date = datetime.fromisoformat(action['appointment']['date'])
        event_end_time = appointment_date + timedelta(hours=1)
        google_api.create_event(
            summary=f"Appointment: {resp['title_in_english']}",
            location=action['appointment']['location'],
            description=f"""
            Summary: {resp['summary_in_english']}
            Required Documents: {action['appointment']['required_documents'] if action['appointment']['required_documents'] else 'None'}
            Additional Notes: {action['appointment']['additional_notes'] if action['appointment']['additional_notes'] else 'None'}
            Document Link: {file_link}
            """,
            start_time=action['appointment']['date'],
            end_time=event_end_time.isoformat()
        )

    elif action['action_type'] == "reply_required":
        deadline_date = datetime.fromisoformat(action['reply']['deadline'])
        event_end_time = deadline_date + timedelta(hours=1)
        google_api.create_event(
            summary=f"Deadline: Reply Required - {resp['title_in_english']}",
            location=action['reply']['address_to_send_to'],
            description=f"""
            Summary: {resp['summary_in_english']}
            Documents to send (Original): {action['reply']['documents_to_send_in_original_language']}
            Documents to send (English): {action['reply']['documents_to_send_in_english']}
            Address: {action['reply']['address_to_send_to']}
            Document Link: {file_link}
            """,
            start_time=action['reply']['deadline'],
            end_time=event_end_time.isoformat()
        )

    elif action['action_type'] == "payment_required":
        # Parse the deadline string back to datetime
        payment_deadline = datetime.fromisoformat(action['payment']['deadline'])
        event_end_time = payment_deadline + timedelta(hours=1)
        google_api.create_event(
            summary=f"Deadline: Payment Required - {resp['title_in_english']}",
            location="",
            description=f"""
            Summary: {resp['summary_in_english']}
            Amount: {action['payment']['amount']}
            Recipient: {action['payment']['recipient']}
            Reference: {action['payment']['reference_number'] if action['payment']['reference_number'] else 'None'}
            Bank Details: {action['payment']['bank_details']}
            """,
            start_time=action['payment']['deadline'],
            end_time=event_end_time.isoformat()
        )

# for action in resp.required_actions:
#     print(f"Action: {action.action_type}")
#     if action.action_type == "appointment":
#         print(f"Appointment: {action.appointment}")
#     elif action.action_type == "reply_required":
#         print(f"Reply required: {action.reply}")
#         print(f"Documents to send in English: {action.reply.documents_to_send_in_english}")
#         print(f"Deadline: {action.reply.deadline}")
#         print(f"Address to send to: {action.reply.address_to_send_to}")
#     elif action.action_type == "payment_required":
#         print(f"Payment required: {action.payment}")
        
