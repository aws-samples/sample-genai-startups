from sqlalchemy import Column, String, Text, DateTime, Boolean, Float, func
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship, foreign
from datetime import datetime
import uuid
from passlib.context import CryptContext

# Password hashing
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# Create base class for SQLAlchemy models
Base = declarative_base()

# Helper function to hash passwords
def get_password_hash(password):
    return pwd_context.hash(password)

# Helper function to verify passwords
def verify_password(plain_password, hashed_password):
    return pwd_context.verify(plain_password, hashed_password)

class Tool(Base):
    """
    Tool model representing a tool that can be used by agents.
    A tool can be a built-in Strands tool, an MCP service, or another agent.
    """
    __tablename__ = 'tool'
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(100), nullable=False)
    description = Column(Text)
    # Tool type: 'builtin', 'mcp', 'agent'
    tool_type = Column(String(20), nullable=False)
    # JSON configuration for the tool
    config = Column(Text)
    # If tool_type is 'agent', this references the agent
    agent_id = Column(UUID(as_uuid=True), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationship with agents that use this tool
    agent_tools = relationship('AgentTool', back_populates='tool',
                              primaryjoin="Tool.id == foreign(AgentTool.tool_id)")

class Agent(Base):
    """
    Agent model representing a Strands agent.
    An agent has a collection of tools and an optional prompt.
    """
    __tablename__ = 'agent'
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(100), nullable=False)
    description = Column(Text)
    prompt = Column(Text)
    model_id = Column(String(100), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Tools that reference this agent
    tools_using_agent = relationship('Tool', backref='agent_reference', 
                                    foreign_keys=[Tool.agent_id],
                                    primaryjoin="Agent.id == foreign(Tool.agent_id)")
    
    # Tools associated with this agent
    agent_tools = relationship('AgentTool', back_populates='agent',
                              primaryjoin="Agent.id == foreign(AgentTool.agent_id)")

class AgentTool(Base):
    """
    Association table for the many-to-many relationship between agents and tools.
    """
    __tablename__ = 'agent_tool'
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    agent_id = Column(UUID(as_uuid=True), nullable=False)
    tool_id = Column(UUID(as_uuid=True), nullable=False)
    # Optional configuration specific to this agent-tool association
    config = Column(Text)

    agent = relationship('Agent', back_populates='agent_tools',
                        primaryjoin="foreign(AgentTool.agent_id) == Agent.id")
    tool = relationship('Tool', back_populates='agent_tools',
                       primaryjoin="foreign(AgentTool.tool_id) == Tool.id")

class Workflow(Base):
    """
    Workflow model representing a directed graph of agents and tools.
    """
    __tablename__ = 'workflow'
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(100), nullable=False)
    description = Column(Text)
    graph_icon = Column(Text)  # Base64 encoded image of the workflow graph
    model_id = Column(String(100), nullable=True)  # Bedrock model ID for the workflow
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    last_edited = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Nodes and edges in this workflow
    nodes = relationship('WorkflowNode', backref='workflow', cascade='all, delete-orphan',
                        primaryjoin="Workflow.id == foreign(WorkflowNode.workflow_id)")
    edges = relationship('WorkflowEdge', backref='workflow', cascade='all, delete-orphan',
                        primaryjoin="Workflow.id == foreign(WorkflowEdge.workflow_id)")

class WorkflowNode(Base):
    """
    Node in a workflow graph. Can represent an agent, tool, input, or output.
    """
    __tablename__ = 'workflow_node'
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    workflow_id = Column(UUID(as_uuid=True), nullable=False)
    # Node type: 'agent', 'tool', 'input', or 'output'
    node_type = Column(String(10), nullable=False)
    # ID of the agent or tool (null for input/output nodes)
    reference_id = Column(UUID(as_uuid=True), nullable=True)
    # Position in the visual builder
    position_x = Column(Float, nullable=False)
    position_y = Column(Float, nullable=False)
    
    # Outgoing and incoming edges
    outgoing_edges = relationship('WorkflowEdge', 
                                 foreign_keys='WorkflowEdge.source_node_id',
                                 backref='source_node',
                                 cascade='all, delete-orphan',
                                 primaryjoin="WorkflowNode.id == foreign(WorkflowEdge.source_node_id)")
    incoming_edges = relationship('WorkflowEdge', 
                                foreign_keys='WorkflowEdge.target_node_id',
                                backref='target_node',
                                cascade='all, delete-orphan',
                                primaryjoin="WorkflowNode.id == foreign(WorkflowEdge.target_node_id)")

class WorkflowEdge(Base):
    """
    Edge in a workflow graph, connecting two nodes.
    """
    __tablename__ = 'workflow_edge'
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    workflow_id = Column(UUID(as_uuid=True), nullable=False)
    source_node_id = Column(UUID(as_uuid=True), nullable=False)
    target_node_id = Column(UUID(as_uuid=True), nullable=False)

class User(Base):
    """
    User model for authentication and profile management.
    """
    __tablename__ = 'user'
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    username = Column(String(100), unique=True, nullable=False)
    password_hash = Column(String(256), nullable=False)
    # Profile type: 'admin', 'configurer', or None (regular user)
    profile_type = Column(String(20), nullable=True)
    is_admin = Column(Boolean, default=False)  # Keeping for backward compatibility
    created_at = Column(DateTime, default=datetime.utcnow)
    
    def set_password(self, password):
        self.password_hash = get_password_hash(password)
        
    def check_password(self, password):
        return verify_password(password, self.password_hash)
    
    @staticmethod
    def get_user_profile(username):
        """
        Get a user's profile by username.
        Returns 'admin', 'configurer', or 'user' (default).
        User named 'admin' always has admin privileges.
        """
        # Hard-code admin privileges for user named 'admin'
        if username == 'admin':
            return 'admin'
            
        user = User.query.filter_by(username=username).first()
        if not user:
            return 'user'  # Default profile for users not in the database
        return user.profile_type or 'user'  # Return 'user' if profile_type is None
