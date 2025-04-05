import logging
import datetime
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger
from apscheduler.jobstores.sqlalchemy import SQLAlchemyJobStore
from spotify_client import SpotifyClient
from youtube_client import YouTubeClient
from converter import AudioToVideoConverter
from config import DEFAULT_CHECK_INTERVAL

logger = logging.getLogger(__name__)

scheduler = None

def init_scheduler(app):
    """Initialize the APScheduler for background tasks."""
    global scheduler
    
    try:
        logger.info("Initializing scheduler...")
        scheduler = BackgroundScheduler()
        
        # Create a job store using SQLAlchemy
        jobstore = SQLAlchemyJobStore(url=app.config['SQLALCHEMY_DATABASE_URI'])
        scheduler.add_jobstore(jobstore, 'default')
        
        # Start the scheduler
        scheduler.start()
        logger.info("Scheduler started successfully.")
        
        # Schedule jobs for all active podcast configurations
        with app.app_context():
            from models import PodcastConfig
            configs = PodcastConfig.query.all()
            
            for config in configs:
                schedule_podcast_check(config)
        
        # Register shutdown handler
        import atexit
        
        @atexit.register
        def shutdown_scheduler():
            if scheduler and scheduler.running:
                logger.info("Shutting down scheduler...")
                scheduler.shutdown()
    except Exception as e:
        logger.error(f"Error initializing scheduler: {str(e)}")
        raise

def schedule_podcast_check(config):
    """Schedule a regular check for new podcast episodes."""
    global scheduler
    
    if not scheduler:
        logger.error("Scheduler not initialized.")
        return False
    
    # Remove any existing jobs for this config
    for job in scheduler.get_jobs():
        if job.id == f"podcast_check_{config.id}":
            job.remove()
    
    # Schedule a new job
    interval_minutes = config.check_interval or DEFAULT_CHECK_INTERVAL
    
    scheduler.add_job(
        check_and_process_new_episodes,
        IntervalTrigger(minutes=interval_minutes),
        id=f"podcast_check_{config.id}",
        args=[config.id],
        replace_existing=True
    )
    
    logger.info(f"Scheduled podcast check for config {config.id} every {interval_minutes} minutes")
    return True

def check_and_process_new_episodes(config_id):
    """Check for new podcast episodes and process them."""
    from app import app, db
    from models import PodcastConfig, ProcessedEpisode, ConversionJob
    
    with app.app_context():
        try:
            # Get the podcast configuration
            config = PodcastConfig.query.get(config_id)
            
            if not config or not config.spotify_podcast_id:
                logger.warning(f"Invalid podcast configuration for ID {config_id}")
                return 0
            
            # Update last check timestamp
            config.last_check = datetime.datetime.utcnow()
            db.session.commit()
            
            # Initialize clients
            spotify_client = SpotifyClient()
            
            # Get latest episodes
            episodes_data = spotify_client.get_podcast_episodes(config.spotify_podcast_id)
            
            if not episodes_data or 'items' not in episodes_data:
                logger.warning(f"No episodes found for podcast {config.spotify_podcast_id}")
                return 0
            
            # Process new episodes
            new_episodes_count = 0
            
            for episode in episodes_data['items']:
                # Check if we've already processed this episode
                existing = ProcessedEpisode.query.filter_by(
                    config_id=config.id, 
                    episode_id=episode['id']
                ).first()
                
                if existing:
                    # Episode already processed
                    continue
                
                # Create a new job for this episode
                job = ConversionJob(
                    user_id=config.user_id,
                    episode_id=episode['id'],
                    status='pending',
                    episode_title=episode['name'],
                    audio_url=episode.get('audio_preview_url', '')
                )
                
                db.session.add(job)
                db.session.commit()
                
                # Create a record for this processed episode
                processed = ProcessedEpisode(
                    config_id=config.id,
                    episode_id=episode['id'],
                    episode_title=episode['name'],
                    episode_url=episode.get('external_urls', {}).get('spotify', '')
                )
                
                db.session.add(processed)
                db.session.commit()
                
                # Process the episode asynchronously
                process_episode_job(job.id)
                
                new_episodes_count += 1
            
            return new_episodes_count
        except Exception as e:
            logger.error(f"Error checking for new episodes: {str(e)}")
            raise

def process_episode_job(job_id):
    """Process a single episode conversion job."""
    from app import app, db
    from models import ConversionJob, PodcastConfig
    
    with app.app_context():
        try:
            # Get the job
            job = ConversionJob.query.get(job_id)
            
            if not job:
                logger.warning(f"Job {job_id} not found")
                return False
            
            # Update job status
            job.status = 'processing'
            job.started_at = datetime.datetime.utcnow()
            db.session.commit()
            
            # Get podcast configuration
            config = PodcastConfig.query.filter_by(user_id=job.user_id).first()
            
            if not config:
                raise ValueError(f"No podcast configuration found for user {job.user_id}")
            
            # Initialize clients
            converter = AudioToVideoConverter()
            youtube_client = YouTubeClient()
            
            # If audio_url is missing, get detailed episode info
            if not job.audio_url:
                spotify_client = SpotifyClient()
                episode_info = spotify_client.get_episode_info(job.episode_id)
                job.audio_url = episode_info.get('audio_preview_url', '')
                db.session.commit()
            
            # Check if we still don't have an audio URL
            if not job.audio_url:
                raise ValueError("Could not retrieve audio URL for episode")
            
            # Process the podcast episode
            logo_url = config.logo_url or "https://via.placeholder.com/1280x720.png?text=Podcast+Episode"
            
            conversion_result = converter.process_podcast_episode(
                audio_url=job.audio_url,
                image_url=logo_url,
                title=job.episode_title,
                width=config.video_width,
                height=config.video_height,
                bitrate=config.video_bitrate
            )
            
            # Save the video path
            job.video_path = conversion_result['video_path']
            db.session.commit()
            
            # Upload to YouTube
            video_description = f"Listen to the full podcast at {config.spotify_podcast_id}"
            
            upload_result = youtube_client.upload_video(
                video_path=conversion_result['video_path'],
                title=job.episode_title,
                description=video_description,
                tags=["podcast", "audio"],
                privacy_status="public"
            )
            
            # Update job with YouTube details
            job.status = 'completed'
            job.youtube_video_id = upload_result['id']
            job.youtube_video_url = upload_result['url']
            job.completed_at = datetime.datetime.utcnow()
            db.session.commit()
            
            # Clean up temporary files
            converter.cleanup_files(
                conversion_result['audio_path'],
                conversion_result['image_path'],
                conversion_result['video_path']
            )
            
            logger.info(f"Successfully processed and uploaded episode: {job.episode_title}")
            return True
        except Exception as e:
            # Update job with error
            if 'job' in locals() and job:
                job.status = 'failed'
                job.error_message = str(e)
                job.completed_at = datetime.datetime.utcnow()
                db.session.commit()
            
            logger.error(f"Error processing episode job {job_id}: {str(e)}")
            return False
