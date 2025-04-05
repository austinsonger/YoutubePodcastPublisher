import os
import logging
import requests
import base64
import json
import time
from config import SPOTIFY_CLIENT_ID, SPOTIFY_CLIENT_SECRET

logger = logging.getLogger(__name__)

class SpotifyClient:
    def __init__(self, client_id=None, client_secret=None):
        # Use provided credentials if available, otherwise fall back to environment variables
        self.client_id = client_id or SPOTIFY_CLIENT_ID
        self.client_secret = client_secret or SPOTIFY_CLIENT_SECRET
        self.access_token = None
        self.token_expiry = 0
        
        if not self.client_id or not self.client_secret:
            logger.warning("Spotify API credentials not found in parameters or environment variables.")
        
        # Get access token immediately upon initialization if credentials are available
        if self.client_id and self.client_secret:
            self._get_access_token()
    
    def _get_access_token(self):
        """Get a new access token from Spotify API."""
        if not self.client_id or not self.client_secret:
            raise ValueError("Spotify API credentials not configured.")
            
        if self.access_token and time.time() < self.token_expiry:
            return self.access_token
            
        # Prepare authorization string
        auth_str = f"{self.client_id}:{self.client_secret}"
        b64_auth = base64.b64encode(auth_str.encode()).decode()
        
        headers = {
            "Authorization": f"Basic {b64_auth}",
            "Content-Type": "application/x-www-form-urlencoded"
        }
        
        payload = {"grant_type": "client_credentials"}
        
        try:
            response = requests.post(
                "https://accounts.spotify.com/api/token",
                headers=headers,
                data=payload
            )
            response.raise_for_status()
            
            token_data = response.json()
            self.access_token = token_data["access_token"]
            self.token_expiry = time.time() + token_data["expires_in"] - 60  # Expire 1 minute early to be safe
            
            return self.access_token
        except requests.exceptions.RequestException as e:
            logger.error(f"Error getting Spotify access token: {str(e)}")
            raise
    
    def _make_api_request(self, endpoint, params=None):
        """Make a request to the Spotify API."""
        # Ensure we have a valid token
        token = self._get_access_token()
        
        headers = {
            "Authorization": f"Bearer {token}"
        }
        
        try:
            url = f"https://api.spotify.com/v1/{endpoint}"
            response = requests.get(url, headers=headers, params=params)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 401:
                # Token expired, get new one and retry
                self.access_token = None
                token = self._get_access_token()
                headers["Authorization"] = f"Bearer {token}"
                response = requests.get(url, headers=headers, params=params)
                response.raise_for_status()
                return response.json()
            else:
                logger.error(f"HTTP error from Spotify API: {str(e)}")
                raise
        except requests.exceptions.RequestException as e:
            logger.error(f"Error making Spotify API request: {str(e)}")
            raise
    
    def get_podcast_info(self, podcast_id):
        """Get information about a specific podcast."""
        try:
            return self._make_api_request(f"shows/{podcast_id}")
        except Exception as e:
            logger.error(f"Error getting podcast info: {str(e)}")
            raise ValueError(f"Could not retrieve podcast information: {str(e)}")
    
    def get_podcast_episodes(self, podcast_id, limit=10):
        """Get episodes for a specific podcast."""
        try:
            params = {
                "limit": limit,
                "market": "US"  # Default market
            }
            return self._make_api_request(f"shows/{podcast_id}/episodes", params)
        except Exception as e:
            logger.error(f"Error getting podcast episodes: {str(e)}")
            raise ValueError(f"Could not retrieve podcast episodes: {str(e)}")
    
    def get_episode_info(self, episode_id):
        """Get detailed information about a specific episode."""
        try:
            return self._make_api_request(f"episodes/{episode_id}")
        except Exception as e:
            logger.error(f"Error getting episode info: {str(e)}")
            raise ValueError(f"Could not retrieve episode information: {str(e)}")
    
    def get_episode_audio_url(self, episode_info):
        """Extract audio URL from episode information."""
        try:
            # The actual audio URL might not be directly accessible from the API
            # Often Spotify doesn't provide direct audio URLs through their API
            # This is a placeholder for a method that would get the actual audio URL
            if "audio_preview_url" in episode_info:
                return episode_info["audio_preview_url"]
            
            # In a real application, you might need to use a library like spotify-dl 
            # or implement a more complex solution to get the actual audio
            raise NotImplementedError("Direct audio download not supported by Spotify API. Consider using a third-party tool.")
        except Exception as e:
            logger.error(f"Error getting episode audio URL: {str(e)}")
            raise
