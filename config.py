import os

# Spotify API configuration
SPOTIFY_CLIENT_ID = os.environ.get('SPOTIFY_CLIENT_ID')
SPOTIFY_CLIENT_SECRET = os.environ.get('SPOTIFY_CLIENT_SECRET')

# YouTube API configuration
YOUTUBE_API_KEY = os.environ.get('YOUTUBE_API_KEY')
YOUTUBE_CLIENT_ID = os.environ.get('YOUTUBE_CLIENT_ID')
YOUTUBE_CLIENT_SECRET = os.environ.get('YOUTUBE_CLIENT_SECRET')
YOUTUBE_REFRESH_TOKEN = os.environ.get('YOUTUBE_REFRESH_TOKEN')

# Temporary file storage
TEMP_DIRECTORY = os.environ.get('TEMP_DIRECTORY', '/tmp/podcast_converter')

# FFmpeg settings
FFMPEG_PATH = os.environ.get('FFMPEG_PATH', 'ffmpeg')

# Default video settings
DEFAULT_VIDEO_WIDTH = 1280
DEFAULT_VIDEO_HEIGHT = 720
DEFAULT_VIDEO_BITRATE = '1M'

# Default check interval (in minutes)
DEFAULT_CHECK_INTERVAL = 60

# Create temp directory if it doesn't exist
if not os.path.exists(TEMP_DIRECTORY):
    os.makedirs(TEMP_DIRECTORY)
