"""
LLM Configurations API endpoints
Provides endpoints for managing LiteLLM and other LLM provider configurations
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List, Dict, Any, Optional
import logging
from datetime import datetime

from app.core.database import get_db
from app.core.auth import get_current_user
from app.models.user import User
from app.models.dataset import LLMConfiguration
from pydantic import BaseModel

logger = logging.getLogger(__name__)

router = APIRouter()


class LLMConfigurationCreate(BaseModel):
    model_config = {"protected_namespaces": ()}
    
    name: str
    provider: str  # 'gemini', 'openai', 'anthropic', 'litellm'
    model_name: str  # 'gemini-2.0-flash', 'gpt-4', etc.
    description: Optional[str] = None
    api_key: Optional[str] = None
    api_base: Optional[str] = None
    model_params: Optional[Dict[str, Any]] = None
    litellm_config: Optional[Dict[str, Any]] = None
    is_default: bool = False


class LLMConfigurationUpdate(BaseModel):
    model_config = {"protected_namespaces": ()}
    
    name: Optional[str] = None
    description: Optional[str] = None
    api_key: Optional[str] = None
    api_base: Optional[str] = None
    model_params: Optional[Dict[str, Any]] = None
    litellm_config: Optional[Dict[str, Any]] = None
    is_active: Optional[bool] = None
    is_default: Optional[bool] = None


class LLMConfigurationResponse(BaseModel):
    model_config = {"protected_namespaces": (), "from_attributes": True}
    
    id: int
    name: str
    provider: str
    model_name: str
    description: Optional[str]
    is_active: bool
    is_default: bool
    api_base: Optional[str]
    total_tokens_used: int
    total_requests: int
    last_used_at: Optional[datetime]
    created_at: datetime
    organization_id: int


class LLMTestRequest(BaseModel):
    message: str = "Hello, can you respond?"


@router.get("/", response_model=List[LLMConfigurationResponse])
async def list_llm_configurations(
    provider: Optional[str] = None,
    active_only: bool = True,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """List LLM configurations for the current organization."""
    if not current_user.organization_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Must belong to an organization"
        )
    
    query = db.query(LLMConfiguration).filter(
        LLMConfiguration.organization_id == current_user.organization_id,
        LLMConfiguration.is_deleted == False
    )
    
    if active_only:
        query = query.filter(LLMConfiguration.is_active == True)
    
    if provider:
        query = query.filter(LLMConfiguration.provider == provider)
    
    configurations = query.order_by(
        LLMConfiguration.is_default.desc(),
        LLMConfiguration.created_at.desc()
    ).all()
    
    return configurations


@router.post("/", response_model=LLMConfigurationResponse)
async def create_llm_configuration(
    config_data: LLMConfigurationCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Create a new LLM configuration."""
    if not current_user.organization_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Must belong to an organization"
        )
    
    # Validate provider
    supported_providers = ['gemini', 'openai', 'anthropic', 'litellm', 'azure', 'cohere']
    if config_data.provider not in supported_providers:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported provider. Supported: {supported_providers}"
        )
    
    # Check for duplicate names in organization
    existing = db.query(LLMConfiguration).filter(
        LLMConfiguration.organization_id == current_user.organization_id,
        LLMConfiguration.name == config_data.name,
        LLMConfiguration.is_deleted == False
    ).first()
    
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="LLM configuration with this name already exists"
        )
    
    # If this is set as default, unset other defaults
    if config_data.is_default:
        db.query(LLMConfiguration).filter(
            LLMConfiguration.organization_id == current_user.organization_id,
            LLMConfiguration.is_default == True
        ).update({"is_default": False})
    
    # Encrypt API key before storing
    from app.core.encryption import encrypt
    encrypted_api_key = encrypt(config_data.api_key) if config_data.api_key else None

    # Create configuration
    db_config = LLMConfiguration(
        name=config_data.name,
        provider=config_data.provider,
        llm_model_name=config_data.model_name,
        description=config_data.description,
        organization_id=current_user.organization_id,
        api_key=encrypted_api_key,  # ✅ Now encrypted
        api_base=config_data.api_base,
        model_params=config_data.model_params,
        litellm_config=config_data.litellm_config,
        is_default=config_data.is_default,
        created_by=current_user.id
    )
    
    db.add(db_config)
    db.commit()
    db.refresh(db_config)
    
    return db_config


@router.get("/{config_id}", response_model=LLMConfigurationResponse)
async def get_llm_configuration(
    config_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get a specific LLM configuration."""
    config = db.query(LLMConfiguration).filter(
        LLMConfiguration.id == config_id,
        LLMConfiguration.organization_id == current_user.organization_id,
        LLMConfiguration.is_deleted == False
    ).first()
    
    if not config:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="LLM configuration not found"
        )
    
    return config


@router.put("/{config_id}", response_model=LLMConfigurationResponse)
async def update_llm_configuration(
    config_id: int,
    config_update: LLMConfigurationUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Update an LLM configuration."""
    config = db.query(LLMConfiguration).filter(
        LLMConfiguration.id == config_id,
        LLMConfiguration.organization_id == current_user.organization_id,
        LLMConfiguration.is_deleted == False
    ).first()
    
    if not config:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="LLM configuration not found"
        )
    
    # If setting as default, unset other defaults
    if config_update.is_default:
        db.query(LLMConfiguration).filter(
            LLMConfiguration.organization_id == current_user.organization_id,
            LLMConfiguration.id != config_id,
            LLMConfiguration.is_default == True
        ).update({"is_default": False})
    
    # Update fields
    update_data = config_update.dict(exclude_unset=True)
    for field, value in update_data.items():
        setattr(config, field, value)
    
    config.updated_at = datetime.utcnow()
    
    db.commit()
    db.refresh(config)
    
    return config


@router.delete("/{config_id}")
async def delete_llm_configuration(
    config_id: int,
    force_delete: bool = False,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Delete an LLM configuration."""
    config = db.query(LLMConfiguration).filter(
        LLMConfiguration.id == config_id,
        LLMConfiguration.organization_id == current_user.organization_id,
        LLMConfiguration.is_deleted == False
    ).first()
    
    if not config:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="LLM configuration not found"
        )
    
    # Don't allow deleting the default configuration
    if config.is_default:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot delete the default LLM configuration"
        )
    
    if force_delete and current_user.is_superuser:
        # Hard delete
        db.delete(config)
    else:
        # Soft delete
        config.soft_delete(current_user.id)
    
    db.commit()
    
    return {"message": "LLM configuration deleted successfully"}


@router.post("/{config_id}/test")
async def test_llm_configuration(
    config_id: int,
    test_request: LLMTestRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Test an LLM configuration."""
    config = db.query(LLMConfiguration).filter(
        LLMConfiguration.id == config_id,
        LLMConfiguration.organization_id == current_user.organization_id,
        LLMConfiguration.is_deleted == False
    ).first()
    
    if not config:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="LLM configuration not found"
        )
    
    # Test the configuration
    try:
        result = await _test_llm_config(config, test_request.message)
        
        # Update usage stats
        config.total_requests += 1
        config.last_used_at = datetime.utcnow()
        
        if result.get("success") and result.get("tokens_used"):
            config.total_tokens_used += result["tokens_used"]
        
        db.commit()
        
        return result
        
    except Exception as e:
        logger.error(f"LLM test failed for config {config_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"LLM test failed: {str(e)}"
        )


@router.get("/providers/supported")
async def get_supported_providers():
    """Get list of supported LLM providers."""
    return {
        "providers": [
            {
                "name": "gemini",
                "display_name": "Google Gemini",
                "models": ["gemini-2.0-flash", "gemini-1.5-pro", "gemini-1.5-flash"],
                "requires_api_key": True
            },
            {
                "name": "openai",
                "display_name": "OpenAI",
                "models": ["gpt-4", "gpt-4-turbo", "gpt-3.5-turbo"],
                "requires_api_key": True
            },
            {
                "name": "anthropic",
                "display_name": "Anthropic Claude",
                "models": ["claude-3-opus", "claude-3-sonnet", "claude-3-haiku"],
                "requires_api_key": True
            },
            {
                "name": "litellm",
                "display_name": "LiteLLM (Universal)",
                "models": ["Any supported by LiteLLM"],
                "requires_api_key": True,
                "description": "Universal interface to 100+ LLMs"
            },
            {
                "name": "azure",
                "display_name": "Azure OpenAI",
                "models": ["gpt-4", "gpt-35-turbo"],
                "requires_api_key": True
            },
            {
                "name": "cohere",
                "display_name": "Cohere",
                "models": ["command-r", "command-r-plus"],
                "requires_api_key": True
            }
        ]
    }


async def _test_llm_config(config: LLMConfiguration, message: str) -> Dict[str, Any]:
    """Test LLM configuration with a sample message."""
    try:
        if config.provider == "litellm":
            return await _test_litellm_config(config, message)
        elif config.provider == "gemini":
            return await _test_gemini_config(config, message)
        elif config.provider == "openai":
            return await _test_openai_config(config, message)
        elif config.provider == "anthropic":
            return await _test_anthropic_config(config, message)
        else:
            return {"success": False, "error": f"Testing not implemented for {config.provider}"}
            
    except Exception as e:
        return {"success": False, "error": str(e)}


async def _test_litellm_config(config: LLMConfiguration, message: str) -> Dict[str, Any]:
    """Test LiteLLM configuration."""
    try:
        import litellm
        
        # Set up LiteLLM configuration
        if config.api_key:
            litellm.api_key = config.api_key
        
        if config.api_base:
            litellm.api_base = config.api_base
        
        # Additional LiteLLM specific config
        if config.litellm_config:
            for key, value in config.litellm_config.items():
                setattr(litellm, key, value)
        
        # Make test call
        response = litellm.completion(
            model=config.llm_model_name,
            messages=[{"role": "user", "content": message}],
            **config.model_params or {}
        )
        
        return {
            "success": True,
            "response": response.choices[0].message.content,
            "model": config.llm_model_name,
            "provider": config.provider,
            "tokens_used": response.usage.total_tokens if response.usage else 0
        }
        
    except Exception as e:
        return {"success": False, "error": f"LiteLLM test failed: {str(e)}"}


async def _test_gemini_config(config: LLMConfiguration, message: str) -> Dict[str, Any]:
    """Test Gemini configuration."""
    try:
        import google.generativeai as genai
        
        genai.configure(api_key=config.api_key)
        model = genai.GenerativeModel(config.llm_model_name)
        
        response = model.generate_content(message)
        
        return {
            "success": True,
            "response": response.text,
            "model": config.llm_model_name,
            "provider": "gemini",
            "tokens_used": getattr(response, 'usage_metadata', {}).get('total_token_count', 0)
        }
        
    except Exception as e:
        return {"success": False, "error": f"Gemini test failed: {str(e)}"}


async def _test_openai_config(config: LLMConfiguration, message: str) -> Dict[str, Any]:
    """Test OpenAI configuration."""
    try:
        import openai
        
        client = openai.OpenAI(
            api_key=config.api_key,
            base_url=config.api_base
        )
        
        response = client.chat.completions.create(
            model=config.llm_model_name,
            messages=[{"role": "user", "content": message}],
            **config.model_params or {}
        )
        
        return {
            "success": True,
            "response": response.choices[0].message.content,
            "model": config.llm_model_name,
            "provider": "openai",
            "tokens_used": response.usage.total_tokens if response.usage else 0
        }
        
    except Exception as e:
        return {"success": False, "error": f"OpenAI test failed: {str(e)}"}


async def _test_anthropic_config(config: LLMConfiguration, message: str) -> Dict[str, Any]:
    """Test Anthropic configuration."""
    try:
        import anthropic
        
        client = anthropic.Anthropic(api_key=config.api_key)
        
        response = client.messages.create(
            model=config.llm_model_name,
            max_tokens=1000,
            messages=[{"role": "user", "content": message}],
            **config.model_params or {}
        )
        
        return {
            "success": True,
            "response": response.content[0].text,
            "model": config.llm_model_name,
            "provider": "anthropic",
            "tokens_used": response.usage.output_tokens + response.usage.input_tokens if response.usage else 0
        }
        
    except Exception as e:
        return {"success": False, "error": f"Anthropic test failed: {str(e)}"} 