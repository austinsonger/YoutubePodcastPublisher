import datetime
from app import db
from flask_login import UserMixin

class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(64), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(256), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.datetime.utcnow)
    
    # Relationships
    podcast_config = db.relationship('PodcastConfig', backref='user', lazy=True, uselist=False)
    conversion_jobs = db.relationship('ConversionJob', backref='user', lazy=True)

class PodcastConfig(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    
    # Spotify settings
    spotify_podcast_id = db.Column(db.String(128))
    
    # YouTube settings
    youtube_channel_id = db.Column(db.String(128))
    
    # Conversion settings
    video_width = db.Column(db.Integer, default=1280)
    video_height = db.Column(db.Integer, default=720)
    video_bitrate = db.Column(db.String(20), default='1M')
    logo_url = db.Column(db.String(512))
    
    # Scheduler settings
    check_interval = db.Column(db.Integer, default=60)  # In minutes
    last_check = db.Column(db.DateTime)
    
    created_at = db.Column(db.DateTime, default=datetime.datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow)

class ProcessedEpisode(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    config_id = db.Column(db.Integer, db.ForeignKey('podcast_config.id'), nullable=False)
    
    # Episode identifiers
    episode_id = db.Column(db.String(128), nullable=False)
    episode_title = db.Column(db.String(512))
    episode_url = db.Column(db.String(512))
    
    processed_at = db.Column(db.DateTime, default=datetime.datetime.utcnow)
    
    # Relationships
    config = db.relationship('PodcastConfig', backref='processed_episodes', lazy=True)

class ConversionJob(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    episode_id = db.Column(db.String(128))
    
    # Status: pending, processing, completed, failed
    status = db.Column(db.String(20), default='pending')
    
    # Job details
    episode_title = db.Column(db.String(512))
    audio_url = db.Column(db.String(512))
    video_path = db.Column(db.String(512))
    youtube_video_id = db.Column(db.String(32))
    youtube_video_url = db.Column(db.String(512))
    
    # Timestamps
    created_at = db.Column(db.DateTime, default=datetime.datetime.utcnow)
    started_at = db.Column(db.DateTime)
    completed_at = db.Column(db.DateTime)
    
    # Error information
    error_message = db.Column(db.Text)
