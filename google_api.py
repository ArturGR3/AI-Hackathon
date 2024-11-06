import datetime
import os.path
import google.auth
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

# If modifying these SCOPES, delete the file token.json.
SCOPES = [
    'https://www.googleapis.com/auth/calendar',
    'https://www.googleapis.com/auth/drive.file',
    'https://www.googleapis.com/auth/tasks'
]

class GoogleAPI:
    def __init__(self):
        self.creds = None
        self.service_calendar = None
        self.service_drive = None
        self.service_tasks = None
        self.authenticate()

    def authenticate(self):
        """Authenticate and create service clients for Calendar, Drive, and Tasks."""
        if os.path.exists('token.json'):
            self.creds = Credentials.from_authorized_user_file('token.json', SCOPES)
        if not self.creds or not self.creds.valid:
            if self.creds and self.creds.expired and self.creds.refresh_token:
                self.creds.refresh(Request())
            else:
                flow = InstalledAppFlow.from_client_secrets_file('credentials.json', SCOPES)
                self.creds = flow.run_local_server(port=0)
            with open('token.json', 'w') as token:
                token.write(self.creds.to_json())
        
        self.service_calendar = build('calendar', 'v3', credentials=self.creds)
        self.service_drive = build('drive', 'v3', credentials=self.creds)
        self.service_tasks = build('tasks', 'v1', credentials=self.creds)

    def create_event(self, summary, location, description, start_time, end_time):
        """Create a calendar event."""
        event = {
            'summary': summary,
            'location': location,
            'description': description,
            'start': {
                'dateTime': start_time,
                'timeZone': 'Europe/Berlin',
            },
            'end': {
                'dateTime': end_time,
                'timeZone': 'Europe/Berlin',
            },
            'reminders': {
                'useDefault': False,
                'overrides': [
                    {'method': 'email', 'minutes': 10},
                    {'method': 'popup', 'minutes': 10},
                ],
            },
        }
        event = self.service_calendar.events().insert(calendarId='primary', body=event).execute()
        print('Event created: %s' % (event.get('htmlLink')))

    def create_drive_folder(self, folder_name, parent_folder_id=None):
        """Create a folder in Google Drive.
        
        Args:
            folder_name (str): Name of the folder to create
            parent_folder_id (str, optional): ID of the parent folder. If None, creates in root.
        """
        file_metadata = {
            'name': folder_name,
            'mimeType': 'application/vnd.google-apps.folder'
        }
        
        # Add parent folder if specified
        if parent_folder_id:
            file_metadata['parents'] = [parent_folder_id]
        
        folder = self.service_drive.files().create(
            body=file_metadata,
            fields='id'
        ).execute()
        
        print(f'Folder "{folder_name}" created with ID: {folder.get("id")}')
        return folder.get('id')

    def upload_pdf(self, folder_id, pdf_file_path, custom_name=None):
        """Upload a PDF file to the specified Google Drive folder.
        
        Args:
            folder_id (str): ID of the folder to upload to
            pdf_file_path (str): Path to the PDF file
            custom_name (str, optional): Custom name for the file
            
        Returns:
            tuple: (file_id, file_name)
        """
        file_name = custom_name if custom_name else os.path.basename(pdf_file_path)
        file_metadata = {
            'name': file_name,
            'parents': [folder_id]
        }
        media = MediaFileUpload(pdf_file_path, mimetype='application/pdf')
        file = self.service_drive.files().create(
            body=file_metadata, 
            media_body=media, 
            fields='id,name'
        ).execute()
        print(f'File uploaded: {file.get("name")} (ID: {file.get("id")})')
        return file.get('id'), file.get('name')

    def create_task(self, task_title, task_notes=None, due_date=None):
        """Create a task in Google Tasks.
        
        Args:
            task_title (str): The title of the task
            task_notes (str, optional): Additional notes for the task
            due_date (str, optional): Due date in RFC 3339 format (e.g., '2024-11-05T12:00:00Z')
        """
        task = {
            'title': task_title,
            'notes': task_notes,
            'due': due_date
        }
        task = self.service_tasks.tasks().insert(tasklist='@default', body=task).execute()
        print('Task created: %s' % (task.get('title')))

    def get_folder_id(self, folder_name, parent_folder_id=None):
        """Get folder ID by name and optional parent folder ID.
        
        Args:
            folder_name (str): Name of the folder to find
            parent_folder_id (str, optional): ID of the parent folder to search in
            
        Returns:
            str: Folder ID if found, None otherwise
        """
        query = f"mimeType='application/vnd.google-apps.folder' and name='{folder_name}' and trashed=false"
        
        if parent_folder_id:
            query += f" and '{parent_folder_id}' in parents"
        
        results = self.service_drive.files().list(
            q=query,
            spaces='drive',
            fields='files(id, name)',
            pageSize=1  # We only need the first match
        ).execute()
        
        files = results.get('files', [])
        return files[0]['id'] if files else None

    def get_or_create_folder(self, folder_name, parent_folder_id=None):
        """Get a folder ID by name, creating it if it doesn't exist.
        
        Args:
            folder_name (str): Name of the folder to find or create
            parent_folder_id (str, optional): ID of the parent folder
            
        Returns:
            str: Folder ID of existing or newly created folder
        """
        folder_id = self.get_folder_id(folder_name, parent_folder_id)
        if folder_id is None:
            folder_id = self.create_drive_folder(folder_name, parent_folder_id)
        return folder_id

def main():
    api = GoogleAPI()
    # Example usage
    api.create_event('Sample Event', '123 Sample St, Sample City, SC', 'This is a sample event created using Python.', 
                     '2024-11-05T10:    00:00-07:00', '2024-11-05T11:00:00-07:00')
    folder_id = api.create_drive_folder('Test')
    api.upload_pdf(folder_id, '/home/artur/github/personal/OCR_learning/scans/1.pdf')
    api.create_task('Sample Task', 'This is a sample task created using Python.', '2024-11-05T12:00:00Z')

if __name__ == '__main__':
    main()