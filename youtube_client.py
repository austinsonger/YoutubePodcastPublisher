import os
import logging
import json
import time
import requests
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
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

class YouTubeClient:
    def __init__(self):
        self.api_key = YOUTUBE_API_KEY
        self.client_id = YOUTUBE_CLIENT_ID
        self.client_secret = YOUTUBE_CLIENT_SECRET
        self.refresh_token = YOUTUBE_REFRESH_TOKEN
        self.youtube = self._authenticate()
    
    def _authenticate(self):
        """Authenticate with YouTube API using OAuth2."""
        if not self.client_id or not self.client_secret or not self.refresh_token:
            logger.warning("YouTube API OAuth credentials not found in environment variables.")
            if self.api_key:
                # Fall back to API key for read-only operations
                logger.info("Using YouTube API key for read-only operations.")
                return build('youtube', 'v3', developerKey=self.api_key)
            else:
                raise ValueError("No YouTube API credentials configured.")
        
        try:
            # Create credentials from refresh token
            credentials = Credentials(
                token=None,
                refresh_token=self.refresh_token,
                token_uri="https://oauth2.googleapis.com/token",
                client_id=self.client_id,
                client_secret=self.client_secret
            )
            
            # Check if the token is expired and refresh if needed
            if credentials.expired:
                credentials.refresh(Request())
            
            # Build the YouTube API client
            return build('youtube', 'v3', credentials=credentials)
        except Exception as e:
            logger.error(f"Error authenticating with YouTube: {str(e)}")
            raise
    
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
