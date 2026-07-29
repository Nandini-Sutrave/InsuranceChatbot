import os
import time
import logging
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional
from app.rag.config import settings
from app.rag.config.settings import LLMProviderType

logger = logging.getLogger(__name__)

# Classified Exceptions Hierarchy
class LLMProviderError(Exception):
    """Base exception for LLM provider errors."""
    pass

class LLMConfigurationError(LLMProviderError):
    """Raised when configuration is missing or invalid."""
    pass

class LLMAuthenticationError(LLMProviderError):
    """Raised when API key or credentials are invalid (non-transient)."""
    pass

class LLMRateLimitError(LLMProviderError):
    """Raised when rate limits are exceeded (transient)."""
    pass

class LLMTimeoutError(LLMProviderError):
    """Raised when request times out (transient)."""
    pass

class LLMServerError(LLMProviderError):
    """Raised when remote server returns error (transient)."""
    pass

class LLMResponseError(LLMProviderError):
    """Raised when LLM response is empty, blocked, or malformed (non-transient)."""
    pass


class BaseLLMProvider(ABC):
    """Interface for LLM providers."""
    
    @abstractmethod
    def generate(self, prompt: str, system_prompt: Optional[str] = None) -> str:
        """Generate text response given an agnostic prompt and optional system instruction."""
        pass
        
    @abstractmethod
    def health_check(self) -> bool:
        """Verify connectivity, credentials, and model availability before generation."""
        pass
        
    @abstractmethod
    def get_metadata(self) -> Dict[str, str]:
        """Return provider metadata (provider name, model, version)."""
        pass


class GeminiProvider(BaseLLMProvider):
    """Google Gemini LLM provider implementation."""
    
    def __init__(self, config: Any):
        self.config = config
        self.api_key = (
            os.getenv("GOOGLE_API_KEY")
            or os.getenv("GEMINI_API_KEY")
            or getattr(config, "GEMINI_API_KEY", "")
        )
        if not self.api_key:
            raise LLMConfigurationError("Gemini API key is not configured.")
            
        import google.generativeai as genai
        self.genai = genai
        try:
            self.genai.configure(api_key=self.api_key)
        except Exception as e:
            raise LLMAuthenticationError(f"Failed to configure Gemini SDK: {e}")
            
        self.model_name = getattr(config, "MODEL_NAME", "gemini-1.5-flash")
        self.temperature = getattr(config, "TEMPERATURE", 0.0)
        self.max_output_tokens = getattr(config, "MAX_OUTPUT_TOKENS", 2048)
        self.request_timeout = getattr(config, "REQUEST_TIMEOUT", 30)
        self.max_retries = getattr(config, "MAX_RETRIES", 1)
        self.model_fallbacks = getattr(config, "MODEL_FALLBACKS", ["gemini-1.5-flash", "gemini-2.0-flash"])
        
    def get_metadata(self) -> Dict[str, str]:
        return {
            "provider_name": "Google Gemini",
            "model": self.model_name,
            "version": "v1beta"
        }
        
    def health_check(self) -> bool:
        if not self.api_key:
            return False
        try:
            # Verify basic client offline model configuration readiness
            self.genai.GenerativeModel(self.model_name)
            return True
        except Exception as e:
            logger.error("Gemini Provider health check failed: %s", e)
            return False
            
    def generate(self, prompt: str, system_prompt: Optional[str] = None) -> str:
        # Check if debug mode is active
        debug_mode = getattr(settings, "LLM_DEBUG_MODE", False)
        
        if debug_mode:
            # 1. Log full request configuration
            api_key_str = self.api_key[:8] if self.api_key else "None"
            sdk_ver = getattr(self.genai, "__version__", "unknown")
            debug_lines = [
                "=== LLM PROVIDER DEBUG PASS ===",
                "- Selected Provider : Google Gemini",
                f"- Model Name        : {self.model_name}",
                f"- API Key Prefix    : {api_key_str}...",
                f"- SDK Version       : {sdk_ver}",
                f"- Temperature       : {self.temperature}",
                f"- Max Output Tokens : {self.max_output_tokens}",
                f"- Request Timeout   : {self.request_timeout}",
                f"- Prompt Length     : {len(prompt)}",
                "==============================="
            ]
            for line in debug_lines:
                logger.info(line)
                print(line)

            # 2. Test invocation comparative check:
            # Test A: With system_instruction
            msg_a = "Attempting Test A: Instantiation with system_instruction..."
            logger.info(msg_a)
            print(msg_a)
            test_a_ok = False
            test_a_res = None
            try:
                model_a = self.genai.GenerativeModel(
                    model_name=self.model_name,
                    system_instruction=system_prompt if system_prompt else None
                )
                res_a = model_a.generate_content(prompt)
                test_a_res = res_a.text
                test_a_ok = True
                ok_msg_a = "Test A (with system_instruction) SUCCEEDED!"
                logger.info(ok_msg_a)
                print(ok_msg_a)
            except Exception as e_a:
                fail_msg_a = f"Test A FAILED! Raw Exception Type: {type(e_a).__name__}, Message: {str(e_a)}"
                logger.error(fail_msg_a)
                print(fail_msg_a)
                
            # Test B: Without system_instruction (Matching verified standalone script)
            msg_b = "Attempting Test B: Instantiation without system_instruction..."
            logger.info(msg_b)
            print(msg_b)
            test_b_ok = False
            test_b_res = None
            try:
                model_b = self.genai.GenerativeModel(model_name=self.model_name)
                res_b = model_b.generate_content(prompt)
                test_b_res = res_b.text
                test_b_ok = True
                ok_msg_b = "Test B (standalone match without system_instruction) SUCCEEDED!"
                logger.info(ok_msg_b)
                print(ok_msg_b)
            except Exception as e_b:
                fail_msg_b = f"Test B FAILED! Raw Exception Type: {type(e_b).__name__}, Message: {str(e_b)}"
                logger.error(fail_msg_b)
                print(fail_msg_b)
                
            # Report result comparison
            if test_a_ok:
                ret_msg_a = "Returning result from Test A (with system_instruction)."
                logger.info(ret_msg_a)
                print(ret_msg_a)
                return test_a_res
            elif test_b_ok:
                ret_msg_b = "Returning result from Test B (without system_instruction)."
                logger.info(ret_msg_b)
                print(ret_msg_b)
                return test_b_res
            else:
                crit_msg = "Both debug invocation paths failed."
                logger.critical(crit_msg)
                print(crit_msg)
                raise LLMProviderError("LLM debug invocation failed on all paths.")
                
        # Production resilient logic (keep all retries and fallbacks intact)
        candidates = [self.model_name] + [fb for fb in self.model_fallbacks if fb != self.model_name]
        
        last_exception = None
        contents = [{"role": "user", "parts": [prompt]}]
        max_attempts = self.max_retries + 1
        
        for attempt in range(1, max_attempts + 1):
            for model_name in candidates:
                try:
                    model = self.genai.GenerativeModel(
                        model_name=model_name,
                        system_instruction=system_prompt if system_prompt else None
                    )
                    config_params = self.genai.types.GenerationConfig(
                        temperature=self.temperature,
                        max_output_tokens=self.max_output_tokens,
                    )
                    res = model.generate_content(contents, generation_config=config_params)
                    
                    # Check for empty, blocked, or malformed responses
                    if not res or not hasattr(res, "text") or not res.text.strip():
                        if hasattr(res, "prompt_feedback") and res.prompt_feedback.block_reason:
                            raise LLMResponseError(f"Gemini generation blocked by safety filters: {res.prompt_feedback.block_reason}")
                        raise LLMResponseError("Gemini returned an empty or malformed response.")
                        
                    return res.text
                    
                except Exception as e:
                    if isinstance(e, LLMResponseError):
                        raise e
                        
                    err_str = str(e).lower()
                    
                    # If this is a model not found / 404 error, we want to try the next fallback candidate model immediately
                    if "not found" in err_str or "404" in err_str or "not_found" in err_str:
                        logger.warning("Model %s not found/supported, trying next fallback model...", model_name)
                        last_exception = LLMConfigurationError(f"Model {model_name} not found or supported: {e}")
                        continue
                        
                    # Classify other exceptions
                    if "rate" in err_str or "429" in err_str or "quota" in err_str:
                        last_exception = LLMRateLimitError(f"Gemini Rate Limit Exceeded: {e}")
                    elif "auth" in err_str or "key" in err_str or "401" in err_str or "403" in err_str:
                        raise LLMAuthenticationError(f"Gemini Authentication Failed: {e}")
                    elif "timeout" in err_str or "deadline" in err_str:
                        last_exception = LLMTimeoutError(f"Gemini Connection Timeout: {e}")
                    elif "500" in err_str or "503" in err_str or "server" in err_str:
                        last_exception = LLMServerError(f"Gemini Server Error: {e}")
                    else:
                        last_exception = LLMProviderError(f"Gemini Generation Failed: {e}")
                        
                    # Break candidates loop to proceed to outer retry for transient failures
                    break
            else:
                # All candidates failed with not found/404 errors, do not retry outer loop
                raise last_exception or LLMConfigurationError("All configured Gemini models failed with not found errors.")
                
            # Outer retry loop handling for transient errors
            if attempt < max_attempts:
                backoff_base = getattr(self.config, "RETRY_BACKOFF_BASE_SECONDS", 1.5)
                sleep_for = backoff_base ** attempt
                logger.warning(
                    "Gemini generation attempt %s failed with transient error: %s. Retrying in %.1fs...",
                    attempt, last_exception, sleep_for,
                )
                time.sleep(sleep_for)
            else:
                logger.error("Gemini generation failed after all retry attempts: %s", last_exception)
                raise last_exception


class MockProvider(BaseLLMProvider):
    """Local mock provider for zero-API/offline evaluations."""
    
    def generate(self, prompt: str, system_prompt: Optional[str] = None) -> str:
        # Mock class returns a failure to trigger the manual context fallback
        raise LLMServerError("Mock provider is active (Zero-API evaluation).")

    def health_check(self) -> bool:
        return True

    def get_metadata(self) -> Dict[str, str]:
        return {
            "provider_name": "Mock Evaluator",
            "model": "mock-zero-api",
            "version": "1.0"
        }


class LLMFactory:
    """Factory to instantiate LLM Providers with dependency injection."""
    
    @staticmethod
    def create(config: Any) -> BaseLLMProvider:
        provider_type = os.getenv("LLM_PROVIDER") or getattr(config, "LLM_PROVIDER", LLMProviderType.GEMINI)
        if isinstance(provider_type, str):
            try:
                provider_type = LLMProviderType(provider_type.lower().strip())
            except ValueError:
                raise LLMConfigurationError(f"Unsupported LLM provider: {provider_type}")
                
        if provider_type == LLMProviderType.MOCK:
            if os.getenv("ENV", "development") == "production":
                raise LLMConfigurationError("Mock provider is not allowed in production environment.")
            return MockProvider()
        elif provider_type == LLMProviderType.GEMINI:
            return GeminiProvider(config)
        else:
            raise LLMConfigurationError(f"Unsupported LLM provider: {provider_type}")
