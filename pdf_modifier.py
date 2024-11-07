from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer
from reportlab.lib.units import inch
import os
from PyPDF2 import PdfMerger
from datetime import datetime
import tempfile

def create_summary_page(doc_info: dict) -> str:
    """
    Creates a PDF page with document summary.
    
    Args:
        doc_info (dict): Document information dictionary containing sender, addressee, summary, etc.
        
    Returns:
        str: Path to the temporary summary PDF file
    """
    # Create a temporary file for the summary page
    temp_summary = tempfile.NamedTemporaryFile(suffix='.pdf', delete=False)
    doc = SimpleDocTemplate(
        temp_summary.name,
        pagesize=letter,
        rightMargin=72,
        leftMargin=72,
        topMargin=72,
        bottomMargin=72
    )

    # Define styles
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        'CustomTitle',
        parent=styles['Heading1'],
        fontSize=16,
        spaceAfter=30,
        textColor=colors.HexColor('#1a237e')
    )
    heading_style = ParagraphStyle(
        'CustomHeading',
        parent=styles['Heading2'],
        fontSize=12,
        textColor=colors.HexColor('#303f9f'),
        spaceAfter=12
    )
    content_style = ParagraphStyle(
        'CustomContent',
        parent=styles['Normal'],
        fontSize=10,
        spaceAfter=20
    )

    # Prepare document content
    story = []
    
    # Title
    story.append(Paragraph("Document Summary", title_style))
    story.append(Spacer(1, 20))

    # Basic Information
    story.append(Paragraph("Sender:", heading_style))
    story.append(Paragraph(doc_info.get('sender', 'N/A'), content_style))
    
    story.append(Paragraph("Addressed To:", heading_style))
    story.append(Paragraph(doc_info.get('addressed_to', 'N/A'), content_style))
    
    story.append(Paragraph("Document Title:", heading_style))
    story.append(Paragraph(doc_info.get('title_in_english', 'N/A'), content_style))
    
    story.append(Paragraph("Summary:", heading_style))
    story.append(Paragraph(doc_info.get('summary_in_english', 'N/A'), content_style))

    # Required Actions
    story.append(Paragraph("Required Actions:", heading_style))
    actions = doc_info.get('required_actions', [])
    if not actions:
        story.append(Paragraph("No actions required", content_style))
    else:
        for action in actions:
            action_type = action.get('action_type', '')
            if action_type == 'appointment':
                appointment = action.get('appointment', {})
                action_text = (
                    f"Appointment:<br/>"
                    f"- Date: {appointment.get('date', 'N/A')}<br/>"
                    f"- Location: {appointment.get('location', 'N/A')}<br/>"
                    f"- Required Documents: {', '.join(appointment.get('required_documents', ['None']))}"
                )
            elif action_type == 'reply_required':
                reply = action.get('reply', {})
                action_text = (
                    f"Reply Required:<br/>"
                    f"- Deadline: {reply.get('deadline', 'N/A')}<br/>"
                    f"- Documents (Original): {', '.join(reply.get('documents_to_send_in_original_language', ['None']))}<br/>"
                    f"- Documents (English): {', '.join(reply.get('documents_to_send_in_english', ['None']))}"
                )
            elif action_type == 'payment_required':
                payment = action.get('payment', {})
                action_text = (
                    f"Payment Required:<br/>"
                    f"- Amount: {payment.get('amount', 'N/A')}<br/>"
                    f"- Deadline: {payment.get('deadline', 'N/A')}<br/>"
                    f"- Recipient: {payment.get('recipient', 'N/A')}"
                )
            else:
                action_text = "No specific action details"
            
            story.append(Paragraph(action_text, content_style))

    # Build the PDF
    doc.build(story)
    return temp_summary.name

def merge_summary_with_original(summary_pdf_path: str, original_pdf_path: str) -> str:
    """
    Merges the summary page with the original PDF.
    
    Args:
        summary_pdf_path (str): Path to the summary PDF
        original_pdf_path (str): Path to the original PDF
        
    Returns:
        str: Path to the merged PDF file
    """
    merger = PdfMerger()
    
    # Add summary page first
    merger.append(summary_pdf_path)
    
    # Add original PDF
    merger.append(original_pdf_path)
    
    # Create output filename
    output_dir = os.path.dirname(original_pdf_path)
    original_filename = os.path.basename(original_pdf_path)
    filename_without_ext = os.path.splitext(original_filename)[0]
    output_path = os.path.join(output_dir, f"{filename_without_ext}_with_summary.pdf")
    
    # Write the merged PDF
    with open(output_path, 'wb') as output_file:
        merger.write(output_file)
    
    # Close the merger
    merger.close()
    
    # Clean up the temporary summary file
    os.unlink(summary_pdf_path)
    
    return output_path

def add_summary_page(doc_info: dict, original_pdf_path: str) -> str:
    """
    Main function to add a summary page to the original PDF.
    
    Args:
        doc_info (dict): Document information dictionary
        original_pdf_path (str): Path to the original PDF file
        
    Returns:
        str: Path to the new PDF with summary page
    """
    # Create summary page
    summary_pdf_path = create_summary_page(doc_info)
    
    # Merge summary with original PDF
    final_pdf_path = merge_summary_with_original(summary_pdf_path, original_pdf_path)
    
    return final_pdf_path 