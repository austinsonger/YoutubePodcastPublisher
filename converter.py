import os
import logging
import subprocess
import tempfile
import requests
import uuid
from datetime import datetime
from config import FFMPEG_PATH, TEMP_DIRECTORY

logger = logging.getLogger(__name__)

class AudioToVideoConverter:
    def __init__(self, ffmpeg_path=None, temp_dir=None):
        self.ffmpeg_path = ffmpeg_path or FFMPEG_PATH
        self.temp_dir = temp_dir or TEMP_DIRECTORY
        
        # Create temp directory if it doesn't exist
        if not os.path.exists(self.temp_dir):
            os.makedirs(self.temp_dir)
    
    def download_audio(self, audio_url):
        """Download an audio file from a URL."""
        try:
            # Generate a unique filename
            audio_filename = f"{uuid.uuid4()}.mp3"
            audio_path = os.path.join(self.temp_dir, audio_filename)
            
            # Download the file
            logger.info(f"Downloading audio from {audio_url}")
            response = requests.get(audio_url, stream=True)
            response.raise_for_status()
            
            with open(audio_path, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    f.write(chunk)
            
            logger.info(f"Audio downloaded to {audio_path}")
            return audio_path
        except Exception as e:
            logger.error(f"Error downloading audio: {str(e)}")
            raise
    
    def download_image(self, image_url):
        """Download an image file from a URL."""
        try:
            # Generate a unique filename
            image_filename = f"{uuid.uuid4()}.jpg"
            image_path = os.path.join(self.temp_dir, image_filename)
            
            # Download the file
            logger.info(f"Downloading image from {image_url}")
            response = requests.get(image_url, stream=True)
            response.raise_for_status()
            
            with open(image_path, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    f.write(chunk)
            
            logger.info(f"Image downloaded to {image_path}")
            return image_path
        except Exception as e:
            logger.error(f"Error downloading image: {str(e)}")
            raise
    
    def convert_audio_to_video(self, audio_path, image_path, output_path=None, width=1280, height=720, bitrate="1M", title=None):
        """Convert audio file to video using a static image."""
        try:
            # Generate output path if not provided
            if not output_path:
                output_filename = f"{uuid.uuid4()}.mp4"
                output_path = os.path.join(self.temp_dir, output_filename)
            
            # Prepare the FFmpeg command
            command = [
                self.ffmpeg_path,
                "-loop", "1",
                "-i", image_path,
                "-i", audio_path,
                "-c:v", "libx264",
                "-tune", "stillimage",
                "-c:a", "aac",
                "-b:a", "192k",
                "-b:v", bitrate,
                "-vf", f"scale={width}:{height}:force_original_aspect_ratio=decrease,pad={width}:{height}:(ow-iw)/2:(oh-ih)/2,format=yuv420p"
            ]
            
            # Add title text if provided
            if title:
                # Simple title at the top of the video
                command.extend([
                    "-vf", f"scale={width}:{height}:force_original_aspect_ratio=decrease,pad={width}:{height}:(ow-iw)/2:(oh-ih)/2,drawtext=text='{title}':fontsize=32:fontcolor=white:x=(w-text_w)/2:y=h-40,format=yuv420p"
                ])
            
            # Set the shortest input to determine the output duration
            command.extend([
                "-shortest",
                "-y",  # Overwrite output file if it exists
                output_path
            ])
            
            # Run the FFmpeg command
            logger.info(f"Converting audio to video: {' '.join(command)}")
            process = subprocess.Popen(
                command,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE
            )
            stdout, stderr = process.communicate()
            
            if process.returncode != 0:
                logger.error(f"FFmpeg error: {stderr.decode()}")
                raise Exception(f"FFmpeg conversion failed: {stderr.decode()}")
            
            logger.info(f"Video created at {output_path}")
            return output_path
        except Exception as e:
            logger.error(f"Error converting audio to video: {str(e)}")
            raise
    
    def process_podcast_episode(self, audio_url, image_url, title=None, width=1280, height=720, bitrate="1M"):
        """Process a podcast episode: download audio, download image, convert to video."""
        try:
            # Download the audio file
            audio_path = self.download_audio(audio_url)
            
            # Download the image file
            image_path = self.download_image(image_url)
            
            # Convert to video
            video_path = self.convert_audio_to_video(
                audio_path=audio_path,
                image_path=image_path,
                width=width,
                height=height,
                bitrate=bitrate,
                title=title
            )
            
            # Return paths for further processing
            return {
                'audio_path': audio_path,
                'image_path': image_path,
                'video_path': video_path
            }
        except Exception as e:
            logger.error(f"Error processing podcast episode: {str(e)}")
            raise
        
    def cleanup_files(self, *file_paths):
        """Clean up temporary files."""
        for path in file_paths:
            if path and os.path.exists(path):
                try:
                    os.remove(path)
                    logger.info(f"Removed temporary file: {path}")
                except Exception as e:
                    logger.warning(f"Failed to remove temporary file {path}: {str(e)}")
