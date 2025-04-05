import os
import logging
import json
import time
import requests
import pickle
from flask import url_for, redirect, session, request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow, Flow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from config import (
    YOUTUBE_API_KEY,
    YOUTUBE_CLIENT_ID,
    YOUTUBE_CLIENT_SECRET,
    YOUTUBE_REFRESH_TOKEN
)

logger = logging.getLogger(__name__)

# OAuth scopes needed for YouTube upload
SCOPES = ['https://www.googleapis.com/auth/youtube.upload', 'https://www.googleapis.com/auth/youtube.readonly']

class YouTubeClient:
    def __init__(self, api_key=None, client_id=None, client_secret=None, refresh_token=None):
        # Use provided credentials if available, otherwise fall back to environment variables
        self.api_key = api_key or YOUTUBE_API_KEY
        self.client_id = client_id or YOUTUBE_CLIENT_ID
        self.client_secret = client_secret or YOUTUBE_CLIENT_SECRET
        self.refresh_token = refresh_token or YOUTUBE_REFRESH_TOKEN
        self.youtube = self._authenticate()
    
    def _authenticate(self):
        """Authenticate with YouTube API using OAuth2."""
        if not self.client_id or not self.client_secret:
            logger.warning("YouTube API OAuth client credentials not found in environment variables.")
            if self.api_key:
                # Fall back to API key for read-only operations
                logger.info("Using YouTube API key for read-only operations.")
                return build('youtube', 'v3', developerKey=self.api_key)
            else:
                raise ValueError("No YouTube API credentials configured.")
        
        try:
            if self.refresh_token:
                # Create credentials from refresh token if available
                credentials = Credentials(
                    token=None,
                    refresh_token=self.refresh_token,
                    token_uri="https://oauth2.googleapis.com/token",
                    client_id=self.client_id,
                    client_secret=self.client_secret,
                    scopes=SCOPES
                )
                
                # Check if the token is expired and refresh if needed
                if credentials.expired:
                    credentials.refresh(Request())
                
                # Build the YouTube API client
                return build('youtube', 'v3', credentials=credentials)
            else:
                # For read-only operations without a refresh token
                if self.api_key:
                    return build('youtube', 'v3', developerKey=self.api_key)
                else:
                    # If we have no tokens at all, return None and require authorization
                    logger.warning("No refresh token available, authorization required.")
                    return None
        except Exception as e:
            logger.error(f"Error authenticating with YouTube: {str(e)}")
            raise
    
    def generate_authorization_url(self, redirect_uri):
        """Generate the authorization URL for YouTube OAuth."""
        try:
            flow = Flow.from_client_config(
                {
                    "web": {
                        "client_id": self.client_id,
                        "client_secret": self.client_secret,
                        "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                        "token_uri": "https://oauth2.googleapis.com/token",
                        "redirect_uris": [redirect_uri]
                    }
                },
                scopes=SCOPES
            )
            
            flow.redirect_uri = redirect_uri
            
            # Generate the authorization URL
            auth_url, _ = flow.authorization_url(
                access_type='offline',
                include_granted_scopes='true',
                prompt='consent'  # Force prompt to ensure refresh token is returned
            )
            
            # Store the flow state in the session or a cache
            # This is important to be able to complete the flow later
            pickled_flow = pickle.dumps(flow)
            session['youtube_auth_flow'] = pickled_flow.hex()
            
            return auth_url
        except Exception as e:
            logger.error(f"Error generating YouTube authorization URL: {str(e)}")
            raise
    
    def handle_authorization_response(self, authorization_response):
        """Handle the authorization response and get tokens."""
        try:
            # Retrieve the flow from the session or cache
            pickled_flow = bytes.fromhex(session.get('youtube_auth_flow', ''))
            flow = pickle.loads(pickled_flow)
            
            # Process the authorization response
            flow.fetch_token(authorization_response=authorization_response)
            
            # Get the credentials
            credentials = flow.credentials
            
            # Store the refresh token
            if credentials.refresh_token:
                self.refresh_token = credentials.refresh_token
                
                # You might want to store this in a more permanent location like a database
                # For now, we'll log it for the user to see
                logger.info(f"YouTube refresh token obtained: {credentials.refresh_token}")
                logger.info("Please set this as the YOUTUBE_REFRESH_TOKEN environment variable.")
                
                # Build the YouTube API client with the new credentials
                self.youtube = build('youtube', 'v3', credentials=credentials)
                
                # Clean up the session
                if 'youtube_auth_flow' in session:
                    del session['youtube_auth_flow']
                
                return {
                    'success': True,
                    'refresh_token': credentials.refresh_token
                }
            else:
                logger.error("No refresh token returned from YouTube API.")
                return {
                    'success': False,
                    'error': 'No refresh token received. Please try again and ensure you approve all permissions.'
                }
        except Exception as e:
            logger.error(f"Error handling YouTube authorization response: {str(e)}")
            return {
                'success': False,
                'error': str(e)
            }
    
    def get_channel_info(self):
        """Get information about the authenticated user's channel."""
        try:
            # Get the authenticated user's channel
            response = self.youtube.channels().list(
                part="snippet,contentDetails,statistics",
                mine=True
            ).execute()
            
            if not response.get('items'):
                raise ValueError("No channel found for the authenticated user.")
            
            channel = response['items'][0]
            return {
                'id': channel['id'],
                'title': channel['snippet']['title'],
                'description': channel['snippet'].get('description', ''),
                'subscribers': channel['statistics'].get('subscriberCount', '0'),
                'videos': channel['statistics'].get('videoCount', '0')
            }
        except Exception as e:
            logger.error(f"Error getting channel info: {str(e)}")
            raise
    
    def upload_video(self, video_path, title, description, tags=None, category_id="22", privacy_status="public"):
        """Upload a video to YouTube."""
        if not os.path.exists(video_path):
            raise FileNotFoundError(f"Video file not found: {video_path}")
        
        try:
            # Create video metadata
            body = {
                'snippet': {
                    'title': title,
                    'description': description,
                    'tags': tags or [],
                    'categoryId': category_id
                },
                'status': {
                    'privacyStatus': privacy_status
                }
            }
            
            # Create an upload request
            media = MediaFileUpload(
                video_path,
                mimetype='video/mp4',
                resumable=True
            )
            
            # Execute the upload
            logger.info(f"Starting upload of video: {title}")
            request = self.youtube.videos().insert(
                part=','.join(body.keys()),
                body=body,
                media_body=media
            )
            
            # Upload the video
            response = None
            while response is None:
                status, response = request.next_chunk()
                if status:
                    logger.info(f"Uploaded {int(status.progress() * 100)}%")
            
            logger.info(f"Video upload complete: {response['id']}")
            
            # Return the uploaded video details
            return {
                'id': response['id'],
                'url': f"https://www.youtube.com/watch?v={response['id']}",
                'title': response['snippet']['title']
            }
        except Exception as e:
            logger.error(f"Error uploading video: {str(e)}")
            raise
    
    def update_video_thumbnail(self, video_id, thumbnail_path):
        """Set a custom thumbnail for a video."""
        if not os.path.exists(thumbnail_path):
            raise FileNotFoundError(f"Thumbnail file not found: {thumbnail_path}")
        
        try:
            # Upload the thumbnail
            media = MediaFileUpload(
                thumbnail_path,
                mimetype='image/jpeg',
                resumable=True
            )
            
            # Set the thumbnail
            self.youtube.thumbnails().set(
                videoId=video_id,
                media_body=media
            ).execute()
            
            logger.info(f"Thumbnail updated for video {video_id}")
            return True
        except Exception as e:
            logger.error(f"Error updating video thumbnail: {str(e)}")
            raise
