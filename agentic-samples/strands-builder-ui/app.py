from multiprocessing import Manager
from fastapi import FastAPI, Request, Response, Depends, HTTPException, Form, status, Cookie
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.engine import URL
from typing import Dict, Any, Optional, List, Union
import uuid
import os
import sys
import boto3
import base64
import json
import bedrock_models
from botocore.exceptions import NoCredentialsError, ClientError
from urllib.parse import quote
from jose import JWTError, jwt
from datetime import datetime, timedelta
import markdown
import bleach
from pygments import highlight
from pygments.formatters import HtmlFormatter
from pygments.lexers import get_lexer_by_name
from functools import wraps
import requests
import traceback

from models import Base, Tool, Agent, Workflow, WorkflowNode, WorkflowEdge, AgentTool, User
from models import get_password_hash, verify_password
from workflow_runner import WorkflowRunner

import multiprocessing 
multiprocessing.set_start_method('spawn', True)  

# Check AWS credentials before app starts
def check_aws_credentials():
    try:
        # Attempt to get caller identity which will fail if credentials are missing or invalid
        sts = boto3.client('sts')
        identity = sts.get_caller_identity()
        if identity:
            return True
    except (NoCredentialsError, ClientError) as e:
        print(f"AWS credential check failed: {str(e)}", file=sys.stderr)
        return False

# Generate DSQL auth token for PostgreSQL connections
def generate_dsql_token(cluster_endpoint, region='us-east-1'):
    """Generate authentication token for DSQL PostgreSQL connections"""
    client = boto3.client("dsql", region_name=region)
    # Use admin token for full access
    token = client.generate_db_connect_admin_auth_token(cluster_endpoint, region)
    return token

# Configure database URI based on environment
def get_database_uri():
    """Get database URI with appropriate authentication"""
    # Default to SQLite if no environment variable is set
    db_uri = os.environ.get('SQLALCHEMY_DATABASE_URI')
    if not db_uri:
        # Use SQLite database
        #make sure instance folder exists
        if not os.path.exists('instance'):
            os.makedirs('instance')
        db_uri = 'sqlite:///instance/strands.db'
    else:
        token = generate_dsql_token(db_uri)
        db_uri = URL.create("postgresql+pg8000", username="admin", password=token, 
        host=db_uri, database="postgres")
    print("DBURI", db_uri)
    return db_uri

# Verify AWS credentials are available
if not check_aws_credentials():
    sys.exit("ERROR: Valid AWS credentials are required to run this application.")
builtin_tools = [
        #{"name": "file_read", "description": "Reading configuration files, parsing code files, loading datasets"},
        #{"name": "file_write", "description": "Writing results to files, creating new files, saving output data"},
        #{"name": "editor", "description": "Advanced file operations like syntax highlighting, pattern replacement, and multi-file edits"},
        #{"name": "shell", "description": "Executing shell commands, interacting with the operating system, running scripts"},
        {"name": "http_request", "description": "Making API calls, fetching web data, sending data to external services"},
        #{"name": "python_repl", "description": "Running Python code snippets, data analysis, executing complex logic"},
        {"name": "calculator", "description": "Performing mathematical operations, symbolic math, equation solving"},
        {"name": "use_aws", "description": "Interacting with AWS services, cloud resource management"},
        {"name": "retrieve", "description": "Retrieving information from Amazon Bedrock Knowledge Bases"},
        #{"name": "nova_reels", "description": "Create high-quality videos using Amazon Bedrock Nova Reel"},
        #{"name": "mem0_memory", "description": "Store user and agent memories across agent runs"},
        {"name": "memory", "description": "Store, retrieve, list, and manage documents in Amazon Bedrock Knowledge Bases"},
        {"name": "environment", "description": "Managing environment variables, configuration management"},
        {"name": "generate_image", "description": "Creating AI-generated images for various applications"},
        #{"name": "image_reader", "description": "Processing and reading image files for AI analysis"},
        {"name": "journal", "description": "Creating structured logs, maintaining documentation"},
        {"name": "think", "description": "Advanced reasoning, multi-step thinking processes"},
        #{"name": "load_tool", "description": "Dynamically loading custom tools and extensions"},
        #{"name": "swarm", "description": "Coordinating multiple AI agents to solve complex problems"},
        {"name": "current_time", "description": "Get the current time in ISO 8601 format"},
        #{"name": "sleep", "description": "Pause execution for the specified number of seconds"},
        #{"name": "agent_graph", "description": "Create and visualize agent relationship graphs"},
        #{"name": "cron", "description": "Schedule and manage recurring tasks with cron job syntax"},
        #{"name": "slack", "description": "Interact with Slack workspace for messaging and monitoring"},
        #{"name": "speak", "description": "Output status messages with rich formatting"},
        {"name": "stop", "description": "Gracefully terminate agent execution with custom message"},
        {"name": "use_llm", "description": "Create nested AI loops with customized system prompts"},
        #{"name": "workflow", "description": "Define, execute, and manage multi-step automated workflows"},
        #{"name": "batch", "description": "Call multiple other tools in parallel"}
    ]
# Database setup
DATABASE_URL = get_database_uri()
engine = create_engine(DATABASE_URL)

# Configure SQLAlchemy to handle PostgreSQL's limitation with DDL statements in transactions
# and disable connection pooling to prevent SSL SYSCALL errors
if 'postgresql' in str(DATABASE_URL):
    engine = create_engine(
        DATABASE_URL,
        isolation_level='AUTOCOMMIT',  # This prevents DDL statements from being wrapped in transactions
        poolclass=None,  # Disable connection pooling
        pool_pre_ping=True,  # Test connections before using them
        pool_recycle=3600  # Recycle connections after an hour as backup
    )

    @event.listens_for(engine, "do_connect")
    def provide_token(dialect, conn_rec, cargs, cparams):
        if os.environ.get('SQLALCHEMY_DATABASE_URI'):
            cparams['password'] = generate_dsql_token(os.environ.get('SQLALCHEMY_DATABASE_URI'))

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Create tables
Base.metadata.create_all(bind=engine)

# Authentication configuration
COGNITO_ENABLED = os.environ.get('COGNITO_ENABLED', 'false').lower() == 'true'
COGNITO_USER_POOL_ID = os.environ.get('COGNITO_USER_POOL_ID', '')
COGNITO_CLIENT_ID = os.environ.get('COGNITO_CLIENT_ID', '')
COGNITO_CLIENT_SECRET = os.environ.get('COGNITO_CLIENT_SECRET', '')
COGNITO_DOMAIN = os.environ.get('COGNITO_DOMAIN', '')
COGNITO_REDIRECT_URI = os.environ.get('COGNITO_REDIRECT_URI', '')
COGNITO_REGION = os.environ.get('AWS_REGION', 'us-east-1')

# JWT settings for session management
SECRET_KEY = os.environ.get('SECRET_KEY', 'dev_key_for_session')
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24  # 24 hours


sync_manager = Manager()
_synced_workflow_queues = sync_manager.dict()

def init_workflow_queues(workflow_id, session_id):
    _synced_workflow_queues[session_id] = sync_manager.dict()
    _synced_workflow_queues[session_id]['input'] = sync_manager.Queue()
    _synced_workflow_queues[session_id]['output'] = sync_manager.Queue()
    _synced_workflow_queues[workflow_id] = session_id
    return _synced_workflow_queues[session_id]
    
def get_workflow_queues( session_id):
    return _synced_workflow_queues.get(session_id)

def get_all_session_for_workflow( workflow_id):
    return [k for k, v in _synced_workflow_queues.items() if v == workflow_id]

def clear_all_workflow_sessions(id_to_clear):
    # Check if the ID is a session ID (conversation ID)
    if id_to_clear in _synced_workflow_queues and isinstance(_synced_workflow_queues[id_to_clear], dict):
        # It's a session ID, terminate and remove it
        _synced_workflow_queues[id_to_clear]['input'].put("_Q_E_E_TERMINATE")
        _synced_workflow_queues.pop(id_to_clear, None)
    else:
        # Assume it's a workflow ID, get all sessions for this workflow
        sessions = get_all_session_for_workflow(id_to_clear) 
        # Send "_Q_E_E_TERMINATE" to all input queues
        for session in sessions:
            # session is a session_id, check if it exists and is a dict
            if session in _synced_workflow_queues and isinstance(_synced_workflow_queues[session], dict):
                _synced_workflow_queues[session]['input'].put("_Q_E_E_TERMINATE")
                _synced_workflow_queues.pop(session, None)
        # Also remove the workflow_id -> session_id mapping
        if id_to_clear in _synced_workflow_queues:
            _synced_workflow_queues.pop(id_to_clear, None)


# FastAPI app
app = FastAPI(title="Strands GUI")

# Mount static files
app.mount("/static", StaticFiles(directory="static"), name="static")

# Templates
templates = Jinja2Templates(directory="templates")

# Add URL helper for static files
def url_for(name: str, **path_params: any) -> str:
    if name == "static":
        filename = path_params.get('filename', '')
        static_url = f"/static/{filename}"
        
        # Check if the file exists
        file_path = os.path.join("static", filename)
        if not os.path.exists(file_path):
            print(f"WARNING: Static file not found: {file_path}")
            # Create a fallback URL that won't cause a 404
            return f"/static/css/style.css"
        else:
            print(f"Static file exists: {file_path}")
            
        return static_url
    elif name == "login":
        return "/login"
    
    try:
        return app.url_path_for(name, **path_params)
    except Exception as e:
        print(f"ERROR: Failed to generate URL for {name} with params {path_params}: {str(e)}")
        # Return a fallback URL
        return "/"

# Make url_for available to templates
templates.env.globals["url_for"] = url_for

# Add filter to decode JWT token and extract username
def decode_jwt_username(token):
    if not token:
        return "Unknown User"
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username = payload.get("username", "Unknown User")
        return username
    except JWTError:
        return "Unknown User"

templates.env.filters["decode_jwt_username"] = decode_jwt_username

# Dependency to get the database session
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# Create default admin user if running locally
def create_default_admin():
    import secrets
    import string
    
    db = SessionLocal()
    try:
        if not COGNITO_ENABLED:
            # Check if admin user exists
            admin = db.query(User).filter_by(username='admin@example.com').first()
            if not admin:
                # Generate random password
                alphabet = string.ascii_letters + string.digits + "!@#$%^&*"
                random_password = ''.join(secrets.choice(alphabet) for _ in range(16))
                
                admin = User(username='admin@example.com', is_admin=True, profile_type='admin')
                admin.set_password(random_password)
                db.add(admin)
                db.commit()
                print("Created default admin user for local development")
                print(f"Admin Password: {random_password}")
            else:
                alphabet = string.ascii_letters + string.digits + "!@#$%^&*"
                random_password = ''.join(secrets.choice(alphabet) for _ in range(16))
                admin.set_password(random_password)
                db.commit()
                print(f"Admin Password: {random_password}")

    finally:
        db.close()

# Create JWT token
def create_access_token(data: dict, expires_delta: Optional[timedelta] = None):
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt

# Get current user from token
async def get_current_user(token: str = Cookie(None), db: Session = Depends(get_db)):
    # Instead of raising an exception, redirect to login page
    login_redirect = RedirectResponse(url="/login", status_code=status.HTTP_302_FOUND)
    
    if not token:
        return login_redirect
    
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id: str = payload.get("sub")
        if user_id is None:
            return login_redirect
    except JWTError:
        return login_redirect
    
    try:
        user_id = uuid.UUID(user_id)
        user = db.query(User).get(user_id)
        if user is None:
            return login_redirect
    except (ValueError, TypeError):
        return login_redirect
    
    return user

# Login required dependency
async def login_required(user = Depends(get_current_user)):
    # If get_current_user returned a RedirectResponse, return it directly
    if isinstance(user, RedirectResponse):
        return user
    return user

# Admin required dependency
async def admin_required(user = Depends(get_current_user)):
    # If get_current_user returned a RedirectResponse, return it directly
    if isinstance(user, RedirectResponse):
        return user
        
    # Otherwise, check if the user has admin privileges
    if user.username == 'admin@example.com' or user.profile_type == 'admin':
        return user
        
    # If not admin, raise a forbidden exception
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="You need administrator privileges to access this resource",
    )

# Configurer required dependency
async def configurer_required(user = Depends(get_current_user)):
    # If get_current_user returned a RedirectResponse, return it directly
    if isinstance(user, RedirectResponse):
        return user
        
    # Otherwise, check if the user has configurer privileges
    if user.profile_type in ['admin', 'configurer']:
        return user
        
    # If not configurer, raise a forbidden exception
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="You need configurer privileges to access this resource",
    )

# Helper function to convert markdown to HTML
def markdown_to_html(text):
    """Convert markdown to HTML with syntax highlighting and sanitization"""
    # Define allowed HTML tags and attributes for bleach
    allowed_tags = [
        'p', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'a', 'abbr', 'acronym', 'b', 'blockquote',
        'code', 'em', 'i', 'li', 'ol', 'ul', 'strong', 'pre', 'span', 'table', 'tbody',
        'td', 'th', 'thead', 'tr', 'img', 'br', 'hr'
    ]
    allowed_attrs = {
        '*': ['class', 'style'],
        'a': ['href', 'title', 'target'],
        'img': ['src', 'alt', 'title', 'width', 'height']
    }
    
    # Custom renderer for code blocks with syntax highlighting
    class HighlightRenderer(markdown.extensions.Extension):
        def extendMarkdown(self, md):
            md.preprocessors.register(HighlightPreprocessor(md), 'highlight', 175)
    
    class HighlightPreprocessor(markdown.preprocessors.Preprocessor):
        def run(self, lines):
            new_lines = []
            in_code_block = False
            code_block_lines = []
            language = ''
            
            for line in lines:
                if line.strip().startswith('```'):
                    if in_code_block:
                        # End of code block
                        in_code_block = False
                        code = '\n'.join(code_block_lines)
                        try:
                            lexer = get_lexer_by_name(language, stripall=True)
                            formatter = HtmlFormatter(style='default', linenos=False, cssclass='codehilite')
                            highlighted_code = highlight(code, lexer, formatter)
                            new_lines.append(highlighted_code)
                        except:
                            # If language not found, just use a generic code block
                            new_lines.append(f'<pre><code>{code}</code></pre>')
                        code_block_lines = []
                    else:
                        # Start of code block
                        in_code_block = True
                        language = line.strip()[3:].strip()  # Get language from ```language
                elif in_code_block:
                    code_block_lines.append(line)
                else:
                    new_lines.append(line)
            
            return new_lines
    
    # Convert markdown to HTML
    html = markdown.markdown(
        text,
        extensions=[
            'markdown.extensions.fenced_code',
            'markdown.extensions.tables',
            'markdown.extensions.nl2br',
            HighlightRenderer()
        ]
    )
    
    # Sanitize HTML
    clean_html = bleach.clean(html, tags=allowed_tags, attributes=allowed_attrs)
    
    return clean_html

# Request logging middleware (Apache-style)
@app.middleware("http")
async def request_logging_middleware(request: Request, call_next):
    import time
    start_time = time.time()
    
    response = await call_next(request)
    
    process_time = time.time() - start_time
    client_ip = request.client.host if request.client else "-"
    method = request.method
    url = str(request.url)
    status_code = response.status_code
    user_agent = request.headers.get("user-agent", "-")
    
    print(f'{client_ip} - - [{time.strftime("%d/%b/%Y:%H:%M:%S %z")}] "{method} {url} HTTP/1.1" {status_code} - "{user_agent}" {process_time:.3f}s')
    
    return response

# No-cache middleware to prevent caching of all responses
@app.middleware("http")
async def no_cache_middleware(request: Request, call_next):
    response = await call_next(request)
    
    # Add no-cache headers to all responses
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    
    return response

# Authentication middleware to redirect unauthenticated users to login page
@app.middleware("http")
async def auth_middleware(request: Request, call_next):
    # Skip auth check for login page, static files, and API endpoints
    if request.url.path == "/login" or request.url.path.startswith("/static"):
        return await call_next(request)
    
    # Check if user is authenticated
    token = request.cookies.get("token")
    is_authenticated = False
    
    if token:
        try:
            payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
            user_id = payload.get("sub")
            if user_id:
                is_authenticated = True
                #print current user
                
        except JWTError:
            pass
    
    # If not authenticated and trying to access a protected page, redirect to login
    if not is_authenticated and request.url.path == "/":
        return RedirectResponse(url="/login", status_code=status.HTTP_302_FOUND)
    
    # Continue with the request
    return await call_next(request)

# Template context processor
@app.middleware("http")
async def add_process_time_header(request: Request, call_next):
    # Add common template variables
    request.state.user_profile = None
    
    # Get user profile from session if available
    token = request.cookies.get("token")
    
    if token:
        try:
            payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
            user_id = payload.get("sub")
            profile_type = payload.get("profile_type")
            
            # Always set user_profile if we have a valid token
            if user_id:
                # If username is admin@example.com, always set profile to admin
                db = SessionLocal()
                try:
                    user = db.query(User).get(uuid.UUID(user_id))
                    if user and user.username == 'admin@example.com':
                        request.state.user_profile = 'admin'
                    else:
                        request.state.user_profile = profile_type or 'user'
                finally:
                    db.close()
        except JWTError as e:
            print("DEBUG: JWT Error:", str(e))
            pass
    
    # Get workflows for navigation
    db = SessionLocal()
    try:
        workflows = db.query(Workflow).all()
        agents = db.query(Agent).all()
        
        # Prepare items for the dropdown with type information
        items = []
        for workflow in workflows:
            items.append({
                'id': workflow.id,
                'name': workflow.name,
                'type': 'workflow'
            })
        for agent in agents:
            items.append({
                'id': agent.id,
                'name': agent.name,
                'type': 'agent'
            })
        
        request.state.workflows = items
    finally:
        db.close()
    
    response = await call_next(request)
    return response

# Routes
@app.get("/favicon.ico")
async def favicon():
    return RedirectResponse(url="/static/favicon.ico")

@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    return templates.TemplateResponse("login.html", {"request": request, "error": None})

@app.post("/login")
async def login(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    db: Session = Depends(get_db)
):
    error = None
    
    if COGNITO_ENABLED:
        # Use Cognito for authentication
        try:
            client = boto3.client('cognito-idp', region_name=COGNITO_REGION)
            response = client.initiate_auth(
                ClientId=COGNITO_CLIENT_ID,
                AuthFlow='USER_PASSWORD_AUTH',
                AuthParameters={
                    'USERNAME': username,
                    'PASSWORD': password
                }
            )
            
            # Get user info
            user_info = client.get_user(
                AccessToken=response['AuthenticationResult']['AccessToken']
            )
            
            # Create or update user in database
            user = db.query(User).filter_by(username=username).first()
            if not user:
                user = User(username=username, profile_type='admin')  # Assume all Cognito users are admins
                user.is_admin = True  # For backward compatibility
                user.set_password('cognito_managed')  # Password is managed by Cognito
                db.add(user)
                db.commit()
            
            # Create access token
            profile_type = 'admin' if username == 'admin@example.com' else (user.profile_type or 'user')
            access_token = create_access_token(
                data={"sub": str(user.id), "username": username, "profile_type": profile_type}
            )
            
            response = RedirectResponse(url="/", status_code=status.HTTP_303_SEE_OTHER)
            response.set_cookie(key="token", value=access_token, httponly=True)
            return response
            
        except Exception as e:
            error = f"Authentication failed: {str(e)}"
    else:
        # Use local authentication
        user = db.query(User).filter_by(username=username).first()
        if user and user.check_password(password):
            # Create access token
            profile_type = 'admin' if username == 'admin@example.com' else (user.profile_type or 'user')
            access_token = create_access_token(
                data={"sub": str(user.id), "username": username, "profile_type": profile_type}
            )
            
            response = RedirectResponse(url="/", status_code=status.HTTP_303_SEE_OTHER)
            response.set_cookie(key="token", value=access_token, httponly=True)
            return response
        else:
            error = "Invalid username or password"
    
    return templates.TemplateResponse("login.html", {"request": request, "error": error})

@app.get("/logout")
async def logout():
    response = RedirectResponse(url="/login", status_code=status.HTTP_303_SEE_OTHER)
    response.delete_cookie(key="token")
    return response

@app.get("/", response_class=HTMLResponse)
async def index(request: Request, user: User = Depends(login_required)):
    return templates.TemplateResponse("chat.html", {"request": request, "workflows": request.state.workflows})

@app.get("/workflows", response_class=HTMLResponse)
async def list_workflows(request: Request, user: User = Depends(configurer_required), db: Session = Depends(get_db)):
    workflows = db.query(Workflow).all()
    return templates.TemplateResponse("workflows.html", {"request": request, "workflows": workflows})

@app.get("/api/workflow/{workflow_id}")
async def get_workflow(workflow_id: uuid.UUID, user: User = Depends(login_required), db: Session = Depends(get_db)):
    workflow = db.query(Workflow).get(workflow_id)
    if not workflow:
        raise HTTPException(status_code=404, detail="Workflow not found")
    
    return {
        "id": workflow.id,
        "name": workflow.name,
        "description": workflow.description,
        "model_id": workflow.model_id,
        "lastEdited": getattr(workflow, 'last_edited', None)
    }

@app.delete("/api/workflow/{workflow_id}")
async def delete_workflow(workflow_id: uuid.UUID, user: User = Depends(login_required), db: Session = Depends(get_db)):
    workflow = db.query(Workflow).get(workflow_id)
    if not workflow:
        raise HTTPException(status_code=404, detail="Workflow not found")
    
    # Clear any active sessions using this workflow
    WorkflowRunner.clear_workflow_sessions(workflow_id)
    
    db.delete(workflow)
    db.commit()
    return {"success": True}

@app.put("/api/workflow/{workflow_id}")
async def update_workflow(
    workflow_id: uuid.UUID, 
    data: Dict[str, Any], 
    user: User = Depends(login_required), 
    db: Session = Depends(get_db)
):
    workflow = db.query(Workflow).get(workflow_id)
    if not workflow:
        raise HTTPException(status_code=404, detail="Workflow not found")
    
    workflow.name = data.get('name', workflow.name)
    workflow.description = data.get('description', workflow.description)
    workflow.model_id = data.get('model_id', workflow.model_id)
    workflow.last_edited = datetime.utcnow()  # Add timestamp for edit
    
    # Generate workflow graph icon if requested
    if data.get('generate_icon', False):
        try:
            # Get the canvas data URL from the request
            canvas_data = data.get('canvas_data')
            if canvas_data and canvas_data.startswith('data:image/'):
                workflow.graph_icon = canvas_data
        except Exception as e:
            print(f"Error generating workflow icon: {str(e)}")
    
    db.commit()
    
    # Clear any active sessions using this workflow
    WorkflowRunner.clear_workflow_sessions(workflow_id)
    
    return {"success": True}

@app.get("/workflow/new", response_class=HTMLResponse)
async def new_workflow_form(request: Request, user: User = Depends(login_required)):
    return templates.TemplateResponse("new_workflow.html", {"request": request})

@app.post("/workflow/new")
async def new_workflow(
    request: Request,
    name: str = Form(...),
    description: str = Form(...),
    model_id: str = Form(None),
    user: User = Depends(login_required),
    db: Session = Depends(get_db)
):
    workflow = Workflow(name=name, description=description, model_id=model_id)
    db.add(workflow)
    db.commit()
    db.refresh(workflow)
    
    return RedirectResponse(url=f"/workflow/{workflow.id}", status_code=status.HTTP_303_SEE_OTHER)

@app.get("/workflow/{workflow_id}", response_class=HTMLResponse)
async def edit_workflow(
    request: Request, 
    workflow_id: uuid.UUID, 
    user: User = Depends(login_required), 
    db: Session = Depends(get_db)
):
    workflow = db.query(Workflow).get(workflow_id)
    if not workflow:
        raise HTTPException(status_code=404, detail="Workflow not found")
    
    agents = db.query(Agent).all()
    # Only show custom tools (MCP and agent tools), not built-in tools
    # Filter out both tools with tool_type='builtin' and tools with description="Built-in Strands tool"
    tools = db.query(Tool).filter(
        (Tool.tool_type != 'builtin') & 
        ((Tool.description != "Built-in Strands tool") | (Tool.description.is_(None)))
    ).all()
    nodes = db.query(WorkflowNode).filter_by(workflow_id=workflow_id).all()
    edges = db.query(WorkflowEdge).filter_by(workflow_id=workflow_id).all()
    
    return templates.TemplateResponse(
        "edit_workflow.html", 
        {
            "request": request, 
            "workflow": workflow, 
            "agents": agents, 
            "tools": tools,
            "nodes": nodes,
            "edges": edges
        }
    )
    workflow = Workflow(name=name, description=description)
    db.add(workflow)
    db.commit()
    db.refresh(workflow)
    
    return RedirectResponse(url=f"/workflow/{workflow.id}", status_code=status.HTTP_303_SEE_OTHER)

log_queue = sync_manager.Queue()

def _process_log_queue():
    while True:
        try:
            log_entry = log_queue.get(block=False)
        except:
            log_entry = None
        if log_entry:
            print(log_entry)
        else:
            break
        
@app.post("/api/workflow/activate/{workflow_id}")
async def activate_workflow(
    workflow_id: uuid.UUID, 
    data: Dict[str, Any], 
    user: User = Depends(login_required),
    db: Session = Depends(get_db)
):
    item_type = data.get('type', 'workflow')

    if item_type == 'agent':
        # Get agent metadata
        agent = db.query(Agent).get(workflow_id)
        if not agent:
            raise HTTPException(status_code=404, detail="Agent not found")
        
        # Use the agent as the orchestrator
        session_id = str(uuid.uuid4())
        qs = init_workflow_queues(workflow_id, session_id)
        print("Starting agent with ID:", workflow_id)
        name = WorkflowRunner.create_threaded_agent(workflow_id, db, qs['input'], qs['output'], log_queue)
        print("Started agent with ID:", workflow_id)
        qs['output'].get()
        _process_log_queue()
        return {
            "success": True,
            "workflow": {
                "id": session_id,
                "name": name
            },
            "metadata": {
                "id": agent.id,
                "name": agent.name,
                "description": agent.description,
                "model_id": agent.model_id,
                "lastEdited": None
            }
        }
    else:
        # Get workflow metadata
        workflow = db.query(Workflow).get(workflow_id)
        if not workflow:
            raise HTTPException(status_code=404, detail="Workflow not found")
        
        # Use the workflow as before
        session_id = str(uuid.uuid4())
        qs = init_workflow_queues(workflow_id, session_id)
        print("Starting workflow with ID:", workflow_id)
        name = WorkflowRunner.create_threaded_workflow(workflow_id, db, qs['input'], qs['output'], log_queue)
        print("Started workflow with ID:", workflow_id)
        qs['output'].get()
        _process_log_queue()
        return {
            "success": True,
            "workflow": {
                "id": session_id,
                "name": name
            },
            "metadata": {
                "id": workflow.id,
                "name": workflow.name,
                "description": workflow.description,
                "model_id": workflow.model_id,
                "lastEdited": getattr(workflow, 'last_edited', None)
            }
        }

@app.post("/api/workflow/reset")
async def reset_workflow(data: Dict[str, Any] = {}, user: User = Depends(login_required)):
    conversation_id = data.get('conversation_id')
    if conversation_id:
        # If conversation_id is provided, clear that specific session
        # This will properly terminate the thread using the conversation ID
        clear_all_workflow_sessions(conversation_id)
    else:
        # For backward compatibility, clear active workflow
        WorkflowRunner.clear_active_workflow()
    _process_log_queue()
    return {"success": True}

@app.post("/api/chat/message")
async def send_message(
    data: Dict[str, Any], 
    user: User = Depends(login_required),
    db: Session = Depends(get_db)
):
    message = data.get('message', '').strip()
    conversation_id = data.get('conversation_id')
    _process_log_queue()
    #get input channel for conversation id
    qs = get_workflow_queues(conversation_id)



    if not message:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={"success": False, "error": "Message cannot be empty"}
        )
    def _event_generator(message=message):
        qs['input'].put(message)
        while True:
            _process_log_queue()
            answer = qs['output'].get()
            if answer == "_Q_E_E_ANSWERED":
                break
            elif answer.startswith("_Q_E_E_HISTORY"):
                # Requeue history messages and sleep
                qs['output'].put(answer)
                import time
                time.sleep(0.2)
                continue
            yield answer    
    try:
        return StreamingResponse(
            _event_generator(),
            media_type="text/plain"
        )
    except ValueError as e:
        if "workflow edited" in str(e).lower():
            return {
                "success": False,
                "workflowEdited": True,
                "error": str(e)
            }
        else:
            return JSONResponse(
                status_code=status.HTTP_400_BAD_REQUEST,
                content={"success": False, "error": str(e)}
            )

@app.post("/api/chat/history")
async def retrieve_conversation_history(
    data: Dict[str, Any], 
    user: User = Depends(login_required)
):
    """Retrieve the full conversation history from the processing thread."""
    conversation_id = data.get('conversation_id')
    
    if not conversation_id:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={"success": False, "error": "Conversation ID is required"}
        )
    
    qs = get_workflow_queues(conversation_id)
    if not qs:
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND,
            content={"success": False, "error": "Conversation not found"}
        )
    
    # Send retrieve message to processing thread
    qs['input'].put("_Q_E_E_RETRIEVE")
    
    # Wait for history response
    while True:
        response = qs['output'].get()
        if response.startswith("_Q_E_E_HISTORY"):
            # Extract JSON from the response
            history_json = response[len("_Q_E_E_HISTORY"):]
            try:
                history = json.loads(history_json)
                return {"success": True, "history": history}
            except json.JSONDecodeError:
                return JSONResponse(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    content={"success": False, "error": "Failed to parse history"}
                )
        elif response == "_Q_E_E_ANSWERED":
            # No history available
            return {"success": True, "history": []}

@app.get("/agents", response_class=HTMLResponse)
async def list_agents(request: Request, user: User = Depends(configurer_required), db: Session = Depends(get_db)):
    agents = db.query(Agent).all()
    return templates.TemplateResponse("agents.html", {"request": request, "agents": agents})

@app.get("/api/agent/{agent_id}")
async def get_agent(agent_id: uuid.UUID, user: User = Depends(login_required), db: Session = Depends(get_db)):
    agent = db.query(Agent).get(agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    
    return {
        "id": agent.id,
        "name": agent.name,
        "description": agent.description,
        "model_id": agent.model_id,
        "lastEdited": None
    }

@app.delete("/api/agent/{agent_id}")
async def delete_agent(agent_id: uuid.UUID, user: User = Depends(login_required), db: Session = Depends(get_db)):
    # Clear any active sessions using this agent
    clear_all_workflow_sessions(agent_id)
    
    # First delete all agent_tool associations for this agent
    db.query(AgentTool).filter_by(agent_id=agent_id).delete()
    
    # Then delete the agent
    agent = db.query(Agent).get(agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    
    db.delete(agent)
    db.commit()
    return {"success": True}

@app.get("/agent/new", response_class=HTMLResponse)
async def new_agent_form(request: Request, user: User = Depends(login_required)):
    return templates.TemplateResponse("new_agent.html", {"request": request})

@app.post("/agent/new")
async def new_agent(
    request: Request,
    name: str = Form(...),
    description: str = Form(...),
    prompt: str = Form(...),
    model_id: str = Form(None),
    user: User = Depends(login_required),
    db: Session = Depends(get_db)
):
    agent = Agent(name=name, description=description, prompt=prompt, model_id=model_id)
    db.add(agent)
    db.commit()
    db.refresh(agent)
    
    return RedirectResponse(url=f"/agent/{agent.id}", status_code=status.HTTP_303_SEE_OTHER)

@app.get("/agent/{agent_id}", response_class=HTMLResponse)
async def edit_agent(
    request: Request, 
    agent_id: uuid.UUID, 
    user: User = Depends(login_required), 
    db: Session = Depends(get_db)
):
    agent = db.query(Agent).get(agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    
    # Get custom tools (MCP and agent tools)
    # Filter out both tools with tool_type='builtin' and tools with description="Built-in Strands tool"
    custom_tools = db.query(Tool).filter(
        (Tool.tool_type != 'builtin') & 
        ((Tool.description != "Built-in Strands tool") | (Tool.description.is_(None)))
    ).all()
    
    # Get default model ID
    default_model_id = bedrock_models.get_default_model_id()
    
    return templates.TemplateResponse(
        "edit_agent.html", 
        {
            "request": request, 
            "agent": agent, 
            "tools": custom_tools, 
            "builtin_tools": builtin_tools,
            "default_model_id": default_model_id
        }
    )

@app.put("/api/agent/{agent_id}")
async def update_agent(
    agent_id: uuid.UUID, 
    data: Dict[str, Any], 
    user: User = Depends(login_required), 
    db: Session = Depends(get_db)
):
    agent = db.query(Agent).get(agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    
    agent.name = data.get('name', agent.name)
    agent.description = data.get('description', agent.description)
    agent.prompt = data.get('prompt', agent.prompt)
    agent.model_id = data.get('model_id', agent.model_id)
    
    db.commit()
    return {"success": True}
    agent = Agent(name=name, description=description, prompt=prompt)
    db.add(agent)
    db.commit()
    db.refresh(agent)
    
    return RedirectResponse(url=f"/agent/{agent.id}", status_code=status.HTTP_303_SEE_OTHER)

@app.get("/tools", response_class=HTMLResponse)
async def list_tools(request: Request, user: User = Depends(configurer_required), db: Session = Depends(get_db)):
    # Only show custom tools (MCP and agent tools), not built-in tools
    # Filter out both tools with tool_type='builtin' and tools with description="Built-in Strands tool"
    tools = db.query(Tool).filter(
        (Tool.tool_type != 'builtin') & 
        ((Tool.description != "Built-in Strands tool") | (Tool.description.is_(None)))
    ).all()
    
    return templates.TemplateResponse("tools.html", {"request": request, "tools": tools})

@app.delete("/api/tool/{tool_id}")
async def delete_tool(tool_id: uuid.UUID, user: User = Depends(login_required), db: Session = Depends(get_db)):
    # First delete all agent_tool associations for this tool
    db.query(AgentTool).filter_by(tool_id=tool_id).delete()
    
    # Then delete the tool
    tool = db.query(Tool).get(tool_id)
    if not tool:
        raise HTTPException(status_code=404, detail="Tool not found")
    
    db.delete(tool)
    db.commit()
    return {"success": True}

@app.get("/tool/new", response_class=HTMLResponse)
async def new_tool_form(request: Request, user: User = Depends(login_required), db: Session = Depends(get_db)):
    agents = db.query(Agent).all()
    return templates.TemplateResponse("new_tool.html", {"request": request, "agents": agents})

@app.post("/tool/new")
async def new_tool(
    request: Request,
    name: str = Form(...),
    description: str = Form(...),
    tool_type: str = Form(...),
    config: str = Form(...),
    agent_id: Optional[str] = Form(None),
    user: User = Depends(login_required),
    db: Session = Depends(get_db)
):
    # Prevent creation of built-in tools through this interface
    if tool_type == 'builtin':
        return RedirectResponse(url="/tools", status_code=status.HTTP_303_SEE_OTHER)
        
    tool = Tool(name=name, description=description, tool_type=tool_type, config=config)
    if agent_id and agent_id != 'null':
        tool.agent_id = uuid.UUID(agent_id)
        
    db.add(tool)
    db.commit()
    db.refresh(tool)
    
    return RedirectResponse(url=f"/tool/{tool.id}", status_code=status.HTTP_303_SEE_OTHER)

@app.get("/tool/{tool_id}", response_class=HTMLResponse)
async def edit_tool(
    request: Request, 
    tool_id: uuid.UUID, 
    user: User = Depends(login_required), 
    db: Session = Depends(get_db)
):
    tool = db.query(Tool).get(tool_id)
    if not tool:
        raise HTTPException(status_code=404, detail="Tool not found")
    
    agents = db.query(Agent).all()
    return templates.TemplateResponse("edit_tool.html", {"request": request, "tool": tool, "agents": agents})

@app.put("/api/tool/{tool_id}")
async def update_tool(
    tool_id: uuid.UUID, 
    data: Dict[str, Any], 
    user: User = Depends(login_required), 
    db: Session = Depends(get_db)
):
    tool = db.query(Tool).get(tool_id)
    if not tool:
        raise HTTPException(status_code=404, detail="Tool not found")
    
    tool.name = data.get('name', tool.name)
    tool.description = data.get('description', tool.description)
    tool.tool_type = data.get('tool_type', tool.tool_type)
    tool.config = data.get('config', tool.config)
    
    # Handle agent_id specifically to avoid NOT NULL constraint issues
    if data.get('tool_type') == 'agent':
        agent_id = data.get('agent_id')
        if agent_id:  # Only set if not None or empty string
            tool.agent_id = uuid.UUID(agent_id)
    else:
        tool.agent_id = None  # Clear agent_id if not an agent tool
    
    db.commit()
    return {"success": True}

@app.post("/api/agent/{agent_id}/tools")
async def add_tool_to_agent(
    agent_id: uuid.UUID, 
    data: Dict[str, Any], 
    user: User = Depends(login_required), 
    db: Session = Depends(get_db)
):
    tool_id = data.get('tool_id')
    tool_name = data.get('tool_name')
    config = data.get('config', '')
    
    agent = db.query(Agent).get(agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    
    # Handle built-in tools (create a Tool record for it)
    if tool_name and not tool_id:
        # Check if this built-in tool already exists
        existing_tool = db.query(Tool).filter_by(name=tool_name, tool_type='builtin').first()
        if existing_tool:
            tool_id = existing_tool.id
        else:
            # Create a new tool record
            #find description from builtin_tools
            description = next((tool['description'] for tool in builtin_tools if tool['name'] == tool_name), None)
            tool = Tool(
                name=tool_name,
                description=description,
                tool_type="builtin",
                config=config
            )
            db.add(tool)
            db.flush()  # Get the ID without committing
            tool_id = tool.id
    
    # Create the association
    if tool_id:
        # Convert tool_id to UUID if it's a string
        if isinstance(tool_id, str):
            tool_id = uuid.UUID(tool_id)
            
        # Check if this tool is already associated with the agent
        existing = db.query(AgentTool).filter_by(agent_id=agent_id, tool_id=tool_id).first()
        if existing:
            return JSONResponse(
                status_code=status.HTTP_400_BAD_REQUEST,
                content={"error": "Tool already added to this agent"}
            )
            
        agent_tool = AgentTool(
            agent_id=agent_id,
            tool_id=tool_id,
            config=config
        )
        db.add(agent_tool)
        db.commit()
        
        # Get the tool name for the response
        tool = db.query(Tool).get(tool_id)
        
        # Determine if this was originally a built-in tool
        is_builtin_source = tool_name and not data.get('tool_id')
        
        return {
            "success": True,
            "tool": {
                "id": tool.id,
                "name": tool.name,
                "type": tool.tool_type,
                "source": "builtin" if is_builtin_source else "custom"
            }
        }
    
    return JSONResponse(
        status_code=status.HTTP_400_BAD_REQUEST,
        content={"error": "Invalid tool information"}
    )

@app.delete("/api/agent/{agent_id}/tools/{tool_id}")
async def remove_tool_from_agent(
    agent_id: uuid.UUID, 
    tool_id: uuid.UUID, 
    user: User = Depends(login_required), 
    db: Session = Depends(get_db)
):
    agent_tool = db.query(AgentTool).filter_by(agent_id=agent_id, tool_id=tool_id).first()
    if not agent_tool:
        raise HTTPException(status_code=404, detail="Tool not found for this agent")
    
    db.delete(agent_tool)
    db.commit()
    return {"success": True}

@app.post("/api/workflow/{workflow_id}/nodes")
async def add_node(
    workflow_id: uuid.UUID, 
    data: Dict[str, Any], 
    user: User = Depends(login_required), 
    db: Session = Depends(get_db)
):
    reference_id = data.get('reference_id')
    if reference_id and data['node_type'] in ['agent', 'tool']:
        reference_id = uuid.UUID(reference_id)
        
    node = WorkflowNode(
        workflow_id=workflow_id,
        node_type=data['node_type'],
        reference_id=reference_id,
        position_x=data['position_x'],
        position_y=data['position_y']
    )
    db.add(node)
    db.commit()
    db.refresh(node)
    
    return {"id": node.id}

@app.post("/api/workflow/{workflow_id}/edges")
async def add_edge(
    workflow_id: uuid.UUID, 
    data: Dict[str, Any], 
    user: User = Depends(login_required), 
    db: Session = Depends(get_db)
):
    edge = WorkflowEdge(
        workflow_id=workflow_id,
        source_node_id=uuid.UUID(data['source_node_id']),
        target_node_id=uuid.UUID(data['target_node_id'])
    )
    db.add(edge)
    db.commit()
    db.refresh(edge)
    
    return {"id": edge.id}

@app.delete("/api/workflow/{workflow_id}/nodes/{node_id}")
async def delete_node(
    workflow_id: uuid.UUID, 
    node_id: uuid.UUID, 
    user: User = Depends(login_required), 
    db: Session = Depends(get_db)
):
    node = db.query(WorkflowNode).get(node_id)
    if not node:
        raise HTTPException(status_code=404, detail="Node not found")
    
    # Also delete any edges connected to this node
    db.query(WorkflowEdge).filter(
        (WorkflowEdge.source_node_id == node_id) | 
        (WorkflowEdge.target_node_id == node_id)
    ).delete()
    
    db.delete(node)
    db.commit()
    return {"success": True}

@app.delete("/api/workflow/{workflow_id}/edges/{edge_id}")
async def delete_edge(
    workflow_id: uuid.UUID, 
    edge_id: uuid.UUID, 
    user: User = Depends(login_required), 
    db: Session = Depends(get_db)
):
    edge = db.query(WorkflowEdge).get(edge_id)
    if not edge:
        raise HTTPException(status_code=404, detail="Edge not found")
    
    db.delete(edge)
    db.commit()
    return {"success": True}

@app.post("/api/tool/mcp/discover")
async def discover_mcp_tools(
    data: Dict[str, Any], 
    user: User = Depends(login_required)
):
    """Discover available tools from MCP configuration."""
    try:
        config = data.get('config', '{}')
        if isinstance(config, str):
            from mcp_helpers import parse_config
            config = parse_config(config)
        
        from strands.tools.mcp import MCPClient
        from mcp import stdio_client, StdioServerParameters
        from mcp_helpers import locate_config
        
        command, args, env, _ = locate_config(config)
        
        if not command:
            return {"success": False, "error": "No command specified in configuration"}
        
        # Create MCP client and use as context manager
        mcp_client = MCPClient(lambda: stdio_client(
            StdioServerParameters(
                command=command,
                args=args,
                env=env
            )
        ))
        
        # Get tools from the MCP server using context manager
        with mcp_client:
            tools = mcp_client.list_tools_sync()
        
        # Extract tool names
        tool_names = [getattr(tool, 'name', getattr(tool, 'tool_name', str(tool))) for tool in tools] if tools else []
        
        return {"success": True, "tools": tool_names}
        
    except Exception as e:
        traceback.print_exc()

        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={"success": False, "error": str(e)}
        )

@app.get("/api/bedrock/models")
async def list_bedrock_models(user: User = Depends(login_required)):
    """Get a list of available Bedrock models with text output modality and on-demand inference."""
    try:
        models = bedrock_models.list_bedrock_models(filter_text_modality=True, filter_on_demand=True)
        default_model = bedrock_models.get_default_model_info()
        
        return {
            "models": models,
            "default_model_id": default_model["id"],
            "default_model_name": default_model["name"]
        }
    except Exception as e:
        traceback.print_exc()
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={"error": f"Failed to list Bedrock models: {str(e)}"}
        )

@app.get("/users", response_class=HTMLResponse)
async def list_users(request: Request, user: User = Depends(admin_required), db: Session = Depends(get_db)):
    users = db.query(User).all()
    return templates.TemplateResponse("users.html", {"request": request, "users": users})

@app.put("/api/user/{user_id}/profile")
async def update_user_profile(
    user_id: uuid.UUID, 
    data: Dict[str, Any], 
    current_user: User = Depends(admin_required), 
    db: Session = Depends(get_db)
):
    user = db.query(User).get(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    profile_type = data.get('profile_type')
    
    # Prevent changing profile for user named 'admin'
    if user.username == 'admin@example.com' and profile_type != 'admin':
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={"error": "Cannot change profile for user 'admin'"}
        )
    
    if profile_type in ['admin', 'configurer', 'user']:
        user.profile_type = 'user' if profile_type == 'user' else profile_type
        # Update is_admin for backward compatibility
        user.is_admin = (profile_type == 'admin')
        db.commit()
        return {"success": True}
    
    return JSONResponse(
        status_code=status.HTTP_400_BAD_REQUEST,
        content={"error": "Invalid profile type"}
    )

@app.post("/api/users")
async def add_user(
    data: Dict[str, Any], 
    current_user: User = Depends(admin_required), 
    db: Session = Depends(get_db)
):
    username = data.get('username')
    password = data.get('password')
    profile_type = data.get('profile_type', 'user')
    
    # Validate input
    if not username or not password:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={"error": "Username and password are required"}
        )
    
    # Check if username already exists
    existing_user = db.query(User).filter_by(username=username).first()
    if existing_user:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={"error": "Username already exists"}
        )
    
    # Create new user
    user = User(
        username=username,
        profile_type=profile_type,
        is_admin=(profile_type == 'admin')
    )
    user.set_password(password)
    
    db.add(user)
    db.commit()
    
    return {"success": True}

@app.put("/api/user/{user_id}/password")
async def reset_user_password(
    user_id: uuid.UUID, 
    data: Dict[str, Any], 
    current_user: User = Depends(admin_required), 
    db: Session = Depends(get_db)
):
    user = db.query(User).get(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    password = data.get('password')
    
    if not password:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={"error": "Password is required"}
        )
    
    user.set_password(password)
    db.commit()
    
    return {"success": True}

create_default_admin()
