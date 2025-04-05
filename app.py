import os
import logging
from flask import Flask, render_template, redirect, url_for, request, flash, session
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.orm import DeclarativeBase
from werkzeug.middleware.proxy_fix import ProxyFix
from werkzeug.security import check_password_hash, generate_password_hash

# Set up logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

class Base(DeclarativeBase):
    pass

# Initialize Flask app and SQLAlchemy
db = SQLAlchemy(model_class=Base)
app = Flask(__name__)
app.secret_key = os.environ.get("SESSION_SECRET")
app.wsgi_app = ProxyFix(app.wsgi_app, x_proto=1, x_host=1)

# Database configuration
app.config["SQLALCHEMY_DATABASE_URI"] = os.environ.get("DATABASE_URL", "sqlite:///podcast_converter.db")
app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {
    "pool_recycle": 300,
    "pool_pre_ping": True,
}
db.init_app(app)

# Initialize login manager
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'
login_manager.login_message = 'Please log in to access this page.'

# Import models and initialize database
with app.app_context():
    from models import User, PodcastConfig, ConversionJob
    db.create_all()

# Import necessary components
from spotify_client import SpotifyClient
from youtube_client import YouTubeClient
from converter import AudioToVideoConverter
from scheduler import init_scheduler

@login_manager.user_loader
def load_user(user_id):
    from models import User
    return User.query.get(int(user_id))

# Routes
@app.route('/')
def index():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
    return redirect(url_for('login'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    from models import User
    
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
        
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        
        user = User.query.filter_by(username=username).first()
        
        if user and check_password_hash(user.password_hash, password):
            login_user(user)
            next_page = request.args.get('next')
            return redirect(next_page or url_for('dashboard'))
        else:
            flash('Invalid username or password.')
    
    return render_template('login.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    from models import User
    
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
        
    if request.method == 'POST':
        username = request.form.get('username')
        email = request.form.get('email')
        password = request.form.get('password')
        
        user_exists = User.query.filter_by(username=username).first()
        email_exists = User.query.filter_by(email=email).first()
        
        if user_exists:
            flash('Username already exists.')
        elif email_exists:
            flash('Email already exists.')
        else:
            new_user = User(
                username=username,
                email=email,
                password_hash=generate_password_hash(password)
            )
            db.session.add(new_user)
            db.session.commit()
            
            login_user(new_user)
            return redirect(url_for('dashboard'))
    
    return render_template('register.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('login'))

@app.route('/dashboard')
@login_required
def dashboard():
    from models import PodcastConfig, ConversionJob
    
    # Get user's podcast configuration
    config = PodcastConfig.query.filter_by(user_id=current_user.id).first()
    
    # Get recent conversion jobs
    recent_jobs = ConversionJob.query.filter_by(user_id=current_user.id).order_by(ConversionJob.created_at.desc()).limit(10).all()
    
    return render_template('dashboard.html', config=config, jobs=recent_jobs)

@app.route('/settings', methods=['GET', 'POST'])
@login_required
def settings():
    from models import PodcastConfig
    
    config = PodcastConfig.query.filter_by(user_id=current_user.id).first()
    
    if request.method == 'POST':
        if not config:
            config = PodcastConfig(user_id=current_user.id)
        
        # Update Spotify configuration
        config.spotify_client_id = request.form.get('spotify_client_id')
        config.spotify_client_secret = request.form.get('spotify_client_secret')
        config.spotify_podcast_id = request.form.get('spotify_podcast_id')
        
        # Update YouTube configuration
        config.youtube_api_key = request.form.get('youtube_api_key')
        config.youtube_client_id = request.form.get('youtube_client_id')
        config.youtube_client_secret = request.form.get('youtube_client_secret')
        if 'youtube_refresh_token' in session:
            config.youtube_refresh_token = session.get('youtube_refresh_token')
        config.youtube_channel_id = request.form.get('youtube_channel_id')
        
        # Update video settings
        config.check_interval = int(request.form.get('check_interval', 60))
        config.video_height = int(request.form.get('video_height', 720))
        config.video_width = int(request.form.get('video_width', 1280))
        config.video_bitrate = request.form.get('video_bitrate', '1M')
        config.logo_url = request.form.get('logo_url')
        
        db.session.add(config)
        db.session.commit()
        
        # Clear the YouTube refresh token from the session if it was saved to the database
        if 'youtube_refresh_token' in session:
            del session['youtube_refresh_token']
            
        flash('Settings updated successfully.')
        return redirect(url_for('settings'))
    
    # If we have a refresh token in the database, add it to the session for display
    if config and config.youtube_refresh_token:
        session['youtube_refresh_token'] = config.youtube_refresh_token
    
    return render_template('settings.html', config=config)

@app.route('/history')
@login_required
def history():
    from models import ConversionJob
    
    # Pagination parameters
    page = request.args.get('page', 1, type=int)
    per_page = 20
    
    # Get user's conversion jobs with pagination
    jobs = ConversionJob.query.filter_by(user_id=current_user.id).order_by(
        ConversionJob.created_at.desc()).paginate(page=page, per_page=per_page)
    
    return render_template('history.html', jobs=jobs)

@app.route('/test_spotify', methods=['POST'])
@login_required
def test_spotify():
    from models import PodcastConfig
    from spotify_client import SpotifyClient
    
    config = PodcastConfig.query.filter_by(user_id=current_user.id).first()
    
    if not config or not config.spotify_podcast_id:
        flash('Please configure your Spotify podcast ID first.')
        return redirect(url_for('settings'))
    
    if not config.spotify_client_id or not config.spotify_client_secret:
        flash('Please provide your Spotify API credentials.')
        return redirect(url_for('settings'))
    
    try:
        # Use the credentials from the database
        spotify_client = SpotifyClient(
            client_id=config.spotify_client_id,
            client_secret=config.spotify_client_secret
        )
        podcast_info = spotify_client.get_podcast_info(config.spotify_podcast_id)
        flash(f'Successfully connected to Spotify. Podcast name: {podcast_info.get("name", "Unknown")}')
    except Exception as e:
        flash(f'Error connecting to Spotify: {str(e)}')
    
    return redirect(url_for('settings'))

@app.route('/test_youtube', methods=['POST'])
@login_required
def test_youtube():
    from youtube_client import YouTubeClient
    from models import PodcastConfig
    
    config = PodcastConfig.query.filter_by(user_id=current_user.id).first()
    
    if not config:
        flash('Please configure your settings first.')
        return redirect(url_for('settings'))
    
    try:
        # Use the credentials from the database
        youtube_client = YouTubeClient(
            api_key=config.youtube_api_key,
            client_id=config.youtube_client_id,
            client_secret=config.youtube_client_secret,
            refresh_token=config.youtube_refresh_token
        )
        
        # If we don't have a refresh token, redirect to authorization
        if not youtube_client.refresh_token and youtube_client.client_id and youtube_client.client_secret:
            return redirect(url_for('youtube_auth'))
        
        # If we have a refresh token, try to use it
        if youtube_client.youtube:
            channel_info = youtube_client.get_channel_info()
            
            # Store the channel ID if it's not already set
            if channel_info and not config.youtube_channel_id:
                config.youtube_channel_id = channel_info.get('id')
                db.session.commit()
                
            flash(f'Successfully connected to YouTube. Channel name: {channel_info.get("title", "Unknown")}')
        else:
            flash('YouTube API client not initialized. Please complete authorization.')
            return redirect(url_for('youtube_auth'))
    except Exception as e:
        flash(f'Error connecting to YouTube: {str(e)}')
    
    return redirect(url_for('settings'))

@app.route('/youtube/auth')
@login_required
def youtube_auth():
    """Start the YouTube OAuth flow."""
    from youtube_client import YouTubeClient
    from models import PodcastConfig
    
    config = PodcastConfig.query.filter_by(user_id=current_user.id).first()
    
    if not config or not config.youtube_client_id or not config.youtube_client_secret:
        flash('Please provide your YouTube API client ID and client secret first.')
        return redirect(url_for('settings'))
    
    try:
        # Use the credentials from the database
        youtube_client = YouTubeClient(
            client_id=config.youtube_client_id,
            client_secret=config.youtube_client_secret
        )
        
        # Generate the authorization URL
        redirect_uri = url_for('youtube_callback', _external=True)
        auth_url = youtube_client.generate_authorization_url(redirect_uri)
        
        # Redirect to Google's OAuth page
        return redirect(auth_url)
    except Exception as e:
        flash(f'Error initiating YouTube authorization: {str(e)}')
        return redirect(url_for('settings'))

@app.route('/youtube/callback')
@login_required
def youtube_callback():
    """Handle the YouTube OAuth callback."""
    from youtube_client import YouTubeClient
    from models import PodcastConfig
    
    config = PodcastConfig.query.filter_by(user_id=current_user.id).first()
    
    if not config:
        flash('Configuration not found.')
        return redirect(url_for('settings'))
    
    try:
        # Get the authorization response URL
        authorization_response = request.url
        
        # Use the credentials from the database
        youtube_client = YouTubeClient(
            client_id=config.youtube_client_id,
            client_secret=config.youtube_client_secret
        )
        
        # Handle the response
        result = youtube_client.handle_authorization_response(authorization_response)
        
        if result['success']:
            # Store the refresh token in the session for the form to display
            session['youtube_refresh_token'] = result['refresh_token']
            
            # Also save it to the database
            config.youtube_refresh_token = result['refresh_token']
            db.session.commit()
            
            flash('YouTube authorization successful! The refresh token has been generated and saved to your settings.')
        else:
            flash(f'YouTube authorization failed: {result.get("error", "Unknown error")}')
    except Exception as e:
        flash(f'Error completing YouTube authorization: {str(e)}')
    
    return redirect(url_for('settings'))

@app.route('/manual_check', methods=['POST'])
@login_required
def manual_check():
    from models import PodcastConfig
    from scheduler import check_and_process_new_episodes
    
    config = PodcastConfig.query.filter_by(user_id=current_user.id).first()
    
    if not config:
        flash('Please configure your settings first.')
        return redirect(url_for('settings'))
    
    try:
        # Run the check function
        result = check_and_process_new_episodes(config.id)
        if result:
            flash(f'Found and processed {result} new episode(s).')
        else:
            flash('No new episodes found.')
    except Exception as e:
        logger.error(f"Error during manual check: {str(e)}")
        flash(f'Error checking for new episodes: {str(e)}')
    
    return redirect(url_for('dashboard'))

# Initialize scheduler
with app.app_context():
    init_scheduler(app)
