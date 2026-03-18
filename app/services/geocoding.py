"""Geocoding via Nominatim with rate limiting; Azure OpenAI fallback for unresolved locations."""
import json
import re
import time
from functools import lru_cache
from typing import Optional, Tuple

import requests

from app.utils.constants import GeocodingConstants
from app.utils.logger import get_coord_logger
from app.utils.log_messages import LogMessages, format_log_message
from app.utils.status_codes import HTTPStatus
from app.utils.resilience import RetryConfig, is_retryable_http_error, retry


class GeocodingService:
    """Geocodes locations via Nominatim; fallback to Azure OpenAI when needed."""

    BASE_URL = GeocodingConstants.NOMINATIM_BASE_URL
    USER_AGENT = GeocodingConstants.USER_AGENT

    def __init__(self) -> None:
        """Initialize rate limit state and optional Azure OpenAI availability check."""
        self.last_request_time = 0
        self.rate_limit_delay = GeocodingConstants.RATE_LIMIT_DELAY
        self.logger, self.emoji_safe = get_coord_logger()
        self._azure_openai_available = self._check_azure_openai_availability()
    
    def _check_azure_openai_availability(self) -> bool:
        """Check if Azure OpenAI is configured"""
        try:
            from app.core.config import get_settings
            settings = get_settings()
            if all([
                settings.azure_openai_key,
                settings.azure_openai_endpoint,
                settings.azure_openai_api_version,
                settings.azure_openai_deployment_name
            ]):
                return True
        except Exception:
            pass
        return False
    
    def _geocode_with_azure_openai(self, location: str) -> Optional[Tuple[float, float]]:
        """
        Geocode location using Azure OpenAI as a fallback when Nominatim fails.
        
        Args:
            location: Location string to geocode
            
        Returns:
            Tuple of (longitude, latitude) or None if not found
        """
        if not self._azure_openai_available:
            return None
        
        try:
            import openai
            from app.core.config import get_settings
            
            settings = get_settings()
            assert settings.azure_openai_endpoint is not None
            assert settings.azure_openai_api_version is not None
            assert settings.azure_openai_deployment_name is not None
            
            # Configure Azure OpenAI
            openai.api_type = "azure"
            openai.api_key = settings.azure_openai_key
            openai.api_base = settings.azure_openai_endpoint
            openai.api_version = settings.azure_openai_api_version
            deployment_name = settings.azure_openai_deployment_name
            
            prompt = GeocodingConstants.AZURE_GEOCODE_USER_TEMPLATE.format(location=location)
            msg = format_log_message(LogMessages.AzureOpenAI.TRYING_GEOCODING, location=location)
            self.logger.info(self.emoji_safe(msg))

            @retry(cfg=RetryConfig(max_attempts=3))
            def _call_openai():
                return openai.ChatCompletion.create(
                    engine=deployment_name,
                    messages=[
                        {"role": "system", "content": GeocodingConstants.AZURE_GEOCODE_SYSTEM},
                        {"role": "user", "content": prompt},
                    ],
                    temperature=0.3,
                    max_tokens=100
                )

            response = _call_openai()
            
            content = response['choices'][0]['message']['content'].strip()
            
            # Remove markdown if present
            if content.startswith("```json"):
                content = content.split("```json")[1].split("```")[0].strip()
            elif content.startswith("```"):
                content = content.split("```")[1].split("```")[0].strip()
            
            # Parse JSON response
            result = json.loads(content)
            
            lat = result.get("latitude")
            lon = result.get("longitude")
            
            if lat is not None and lon is not None:
                try:
                    lat_f = float(lat)
                    lon_f = float(lon)
                    
                    # Validate coordinates
                    if -90 <= lat_f <= 90 and -180 <= lon_f <= 180:
                        msg = format_log_message(LogMessages.AzureOpenAI.GEOCODED_SUCCESS, location=location, lat=lat_f, lon=lon_f)
                        self.logger.info(self.emoji_safe(msg))
                        return (lon_f, lat_f)  # Return (longitude, latitude)
                except (ValueError, TypeError):
                    pass
            
            msg = format_log_message(LogMessages.AzureOpenAI.COULD_NOT_GEOCODE, location=location)
            self.logger.info(self.emoji_safe(msg))
            return None
            
        except ImportError:
            msg = LogMessages.AzureOpenAI.LIBRARY_NOT_INSTALLED
            self.logger.warning(self.emoji_safe(msg))
            return None
        except json.JSONDecodeError as e:
            msg = format_log_message(LogMessages.AzureOpenAI.FAILED_TO_PARSE_RESPONSE, location=location, error=str(e))
            self.logger.warning(self.emoji_safe(msg))
            return None
        except Exception as e:
            msg = format_log_message(LogMessages.AzureOpenAI.GEOCODING_ERROR, location=location, error=str(e))
            self.logger.warning(self.emoji_safe(msg))
            return None
    
    def _respect_rate_limit(self):
        """Ensure we don't exceed 1 request per second"""
        current_time = time.time()
        time_since_last = current_time - self.last_request_time
        if time_since_last < self.rate_limit_delay:
            sleep_time = self.rate_limit_delay - time_since_last
            msg = format_log_message(LogMessages.Geocoding.RATE_LIMITING, sleep_time=sleep_time)
            self.logger.debug(self.emoji_safe(msg))
            time.sleep(sleep_time)
        self.last_request_time = time.time()
    
    def _extract_coordinates_from_result(self, result: dict) -> Tuple[float | None, float | None]:
        """Extract coordinates from Nominatim API result."""
        lon = None
        lat = None
        
        # Try 'lon' and 'lat' first
        if 'lon' in result and 'lat' in result:
            try:
                lon = float(result['lon'])
                lat = float(result['lat'])
            except (ValueError, TypeError):
                pass
        
        # If that fails, try 'longitude' and 'latitude'
        if lon is None or lat is None:
            if 'longitude' in result and 'latitude' in result:
                try:
                    lon = float(result['longitude'])
                    lat = float(result['latitude'])
                except (ValueError, TypeError):
                    pass
        
        return lon, lat
    
    def _validate_coordinates(self, lon: float | None, lat: float | None, location: str) -> bool:
        """Validate coordinate values. Returns True if valid."""
        if lon is None or lat is None or lon == 0 or lat == 0:
            msg = format_log_message(LogMessages.Geocoding.INVALID_COORDINATES_RETURNED, location=location, lon=lon, lat=lat)
            self.logger.warning(self.emoji_safe(msg))
            return False
        
        if not (-180 <= lon <= 180 and -90 <= lat <= 90):
            msg = format_log_message(LogMessages.Geocoding.INVALID_COORDINATE_RANGE, location=location, lon=lon, lat=lat)
            self.logger.warning(self.emoji_safe(msg))
            return False
        
        return True
    
    def _handle_successful_response(self, data: list, location: str) -> Optional[Tuple[float, float]]:
        """Handle successful API response."""
        if not data or len(data) == 0:
            msg = format_log_message(LogMessages.Geocoding.NO_RESULTS_FOUND, location=location)
            self.logger.debug(self.emoji_safe(msg))
            return None
        
        result = data[0]
        lon, lat = self._extract_coordinates_from_result(result)
        
        if not self._validate_coordinates(lon, lat, location):
            return None

        assert lon is not None
        assert lat is not None
        
        msg = format_log_message(LogMessages.Geocoding.SUCCESSFULLY_GEOCODED, location=location, lon=lon, lat=lat)
        self.logger.debug(self.emoji_safe(msg))
        return (lon, lat)
    
    def _handle_error_response(self, status_code: int, location: str) -> None:
        """Handle error API responses."""
        if status_code == 403:
            msg = format_log_message(LogMessages.Geocoding.ACCESS_FORBIDDEN, location=location)
            self.logger.error(self.emoji_safe(msg))
            time.sleep(GeocodingConstants.EXTRA_DELAY_AFTER_403)
        else:
            msg = format_log_message(LogMessages.Geocoding.GEOCODING_API_ERROR, location=location, status_code=status_code)
            self.logger.error(self.emoji_safe(msg))
    
    def _make_geocoding_request(self, location: str) -> Optional[requests.Response]:
        """Make geocoding API request. Returns response or None on error."""
        self._respect_rate_limit()
        
        params: dict[str, str | int] = {
            "q": location.strip(),
            "format": "json",
            "limit": 1,
            "addressdetails": 0,
        }
        
        headers = {'User-Agent': self.USER_AGENT}
        
        msg = format_log_message(LogMessages.Geocoding.GEOCODING_REQUEST, location=location)
        self.logger.debug(self.emoji_safe(msg))
        
        try:
            @retry(cfg=RetryConfig(max_attempts=4), is_retryable=is_retryable_http_error)
            def _get() -> requests.Response:
                resp = requests.get(
                    self.BASE_URL,
                    params=params,
                    headers=headers,
                    timeout=(GeocodingConstants.TIMEOUT_CONNECT, GeocodingConstants.TIMEOUT_READ),
                    verify=True
                )
                if resp.status_code >= 400:
                    resp.raise_for_status()
                return resp

            return _get()
        except requests.exceptions.Timeout:
            msg = format_log_message(LogMessages.Geocoding.TIMEOUT_GEOCODING, location=location)
            self.logger.warning(self.emoji_safe(msg))
            return None
        except requests.exceptions.ConnectionError:
            msg = format_log_message(LogMessages.Geocoding.CONNECTION_ERROR, location=location)
            self.logger.warning(self.emoji_safe(msg))
            return None
        except requests.exceptions.HTTPError as e:
            status = getattr(getattr(e, "response", None), "status_code", None)
            if status == 403:
                # Preserve existing behavior for Nominatim block behavior
                msg = format_log_message(LogMessages.Geocoding.ACCESS_FORBIDDEN, location=location)
                self.logger.error(self.emoji_safe(msg))
                time.sleep(GeocodingConstants.EXTRA_DELAY_AFTER_403)
                return None
            msg = format_log_message(LogMessages.Geocoding.GEOCODING_API_ERROR, location=location, status_code=status)
            self.logger.error(self.emoji_safe(msg))
            return None
        except requests.exceptions.RequestException as e:
            msg = format_log_message(LogMessages.Geocoding.REQUEST_ERROR, location=location, error=str(e))
            self.logger.error(self.emoji_safe(msg))
            return None
    
    @lru_cache(maxsize=1000)
    def get_coordinates(self, location: str) -> Optional[Tuple[float, float]]:
        """
        Get coordinates for a location using Nominatim API
        
        Args:
            location: Location string to geocode
            
        Returns:
            Tuple of (longitude, latitude) or None if not found
        """
        if not location or not location.strip():
            return None
        
        try:
            response = self._make_geocoding_request(location)
            if not response:
                return None
            
            if response.status_code == HTTPStatus.OK:
                data = response.json()
                return self._handle_successful_response(data, location)
            
            self._handle_error_response(response.status_code, location)
            return None
                
        except (ValueError, KeyError, IndexError) as e:
            msg = format_log_message(LogMessages.Geocoding.DATA_PARSING_ERROR, location=location, error=str(e))
            self.logger.error(self.emoji_safe(msg))
            return None
        except KeyboardInterrupt:
            raise
        except Exception as e:
            msg = format_log_message(LogMessages.Geocoding.UNEXPECTED_ERROR, location=location, error=str(e))
            self.logger.error(self.emoji_safe(msg))
            return None
    
    def _remove_prefixes(self, location: str) -> str:
        """Remove common prefixes from location string."""
        cleaned_location = location.strip()
        prefixes_to_remove = ['near ', 'close to ', 'around ', 'in ', 'at ']
        for prefix in prefixes_to_remove:
            if cleaned_location.lower().startswith(prefix.lower()):
                cleaned_location = cleaned_location[len(prefix):].strip()
                break
        return cleaned_location
    
    def _try_cleaned_location(self, location: str, cleaned_location: str) -> Optional[Tuple[float, float]]:
        """Try geocoding with cleaned location (prefixes removed)."""
        if cleaned_location != location:
            coords = self.get_coordinates(cleaned_location)
            if coords:
                msg = format_log_message(LogMessages.Geocoding.FOUND_COORDINATES_CLEANED, location=location, cleaned_location=cleaned_location)
                self.logger.debug(self.emoji_safe(msg))
                return coords
        return None
    
    def _try_comma_separated_parts(self, location: str, cleaned_location: str) -> Optional[Tuple[float, float]]:
        """Try geocoding with comma-separated parts individually and in combinations."""
        if ',' not in cleaned_location:
            return None
        
        parts = [part.strip() for part in cleaned_location.split(',')]
        
        # Try each part individually
        for i, part in enumerate(parts):
            if part and part != cleaned_location:
                coords = self.get_coordinates(part)
                if coords:
                    msg = format_log_message(LogMessages.Geocoding.FOUND_COORDINATES_PART, location=location, part_num=i+1, part=part)
                    self.logger.debug(self.emoji_safe(msg))
                    return coords
        
        # Try combinations of parts
        for i in range(len(parts) - 1):
            combined = f"{parts[i]}, {parts[i+1]}"
            if combined != cleaned_location:
                coords = self.get_coordinates(combined)
                if coords:
                    msg = format_log_message(LogMessages.Geocoding.FOUND_COORDINATES_COMBINED, location=location, combined=combined)
                    self.logger.debug(self.emoji_safe(msg))
                    return coords
        
        return None
    
    def _simplify_location(self, location: str) -> str:
        """Simplify location by removing common descriptive words."""
        common_words_to_remove = [
            'district', 'village', 'villages', 'town', 'city', 'municipality',
            'taluk', 'tehsil', 'block', 'area', 'region', 'zone', 'ward',
            'various', 'multiple', 'several', 'many', 'some', 'valley', 'wildlife', 'few',
            'riverbank', 'riverbanks', 'river', 'rivers', 'stream', 'streams',
            'lake', 'lakes', 'pond', 'ponds', 'waterfall', 'waterfalls',
            'mountain', 'mountains', 'hill', 'hills', 'peak', 'peaks',
            'beach', 'beaches', 'coast', 'coastal', 'shore', 'shores',
            'forest', 'forests', 'jungle', 'jungles', 'park', 'parks',
            'temple', 'temples', 'monument', 'monuments', 'fort', 'forts',
            'palace', 'palaces', 'museum', 'museums', 'garden', 'gardens',
            'market', 'markets', 'bazaar', 'bazaars', 'mall', 'malls',
            'station', 'stations', 'airport', 'airports', 'port', 'ports',
            'bridge', 'bridges', 'road', 'roads', 'street', 'streets',
            'square', 'squares', 'circle', 'circles', 'crossing', 'crossings',
            'riverside', 'outskirts', 'center', 'centers', 'sanctuary', 'national'
        ]
        
        from app.utils.security import validate_input_length, MAX_LOCATION_INPUT_LENGTH
        try:
            simplified_location = validate_input_length(location, MAX_LOCATION_INPUT_LENGTH)
        except (ValueError, TypeError):
            simplified_location = location[:MAX_LOCATION_INPUT_LENGTH] if location else ""
        
        for word in common_words_to_remove:
            pattern = r'\b' + re.escape(word) + r'\b'
            simplified_location = re.sub(pattern, '', simplified_location, count=1, flags=re.IGNORECASE)
        
        # Clean up extra spaces and commas using safer patterns
        # Use non-backtracking patterns to prevent ReDoS
        # Replace multiple spaces (2+) with single space - limit to reasonable number
        simplified_location = re.sub(r'\s{2,10}', ' ', simplified_location).strip()
        # Remove leading separators - use specific character classes without quantifiers
        while simplified_location and simplified_location[0] in ',; \t\n\r':
            simplified_location = simplified_location[1:]
        # Remove trailing separators - use specific character classes without quantifiers
        while simplified_location and simplified_location[-1] in ',; \t\n\r':
            simplified_location = simplified_location[:-1]
        
        return simplified_location
    
    def _try_simplified_location(self, location: str) -> Optional[Tuple[float, float]]:
        """Try geocoding with simplified location (common words removed)."""
        simplified_location = self._simplify_location(location)
        if simplified_location and simplified_location != location:
            msg = format_log_message(LogMessages.Geocoding.TRYING_SIMPLIFIED_LOCATION, simplified_location=simplified_location)
            self.logger.debug(self.emoji_safe(msg))
            coords = self.get_coordinates(simplified_location)
            if coords:
                return coords
        return None
    
    def _try_main_location(self, location: str, cleaned_location: str) -> Optional[Tuple[float, float]]:
        """Try geocoding with main location (before first comma)."""
        if ',' not in cleaned_location:
            return None
        
        main_location = cleaned_location.split(',')[0].strip()
        if main_location != cleaned_location:
            coords = self.get_coordinates(main_location)
            if coords:
                msg = format_log_message(LogMessages.Geocoding.FOUND_COORDINATES_MAIN, location=location, main_location=main_location)
                self.logger.debug(self.emoji_safe(msg))
                return coords
        return None
    
    def _try_country_suffixes(self, location: str, cleaned_location: str) -> Optional[Tuple[float, float]]:
        """Try geocoding with country suffixes."""
        common_suffixes = [
            f"{cleaned_location}, Jordan",
            f"{cleaned_location}, Amman, Jordan",
            f"{cleaned_location}, India",
            f"{cleaned_location}, USA", 
            f"{cleaned_location}, UK",
        ]
        
        for suffix_location in common_suffixes:
            coords = self.get_coordinates(suffix_location)
            if coords:
                msg = format_log_message(LogMessages.Geocoding.FOUND_COORDINATES_FALLBACK, location=location, suffix_location=suffix_location)
                self.logger.debug(self.emoji_safe(msg))
                return coords
        return None
    
    def _try_azure_openai_fallback(self, location: str) -> Optional[Tuple[float, float]]:
        """Try geocoding with Azure OpenAI as final fallback."""
        if not self._azure_openai_available:
            msg = format_log_message(LogMessages.AzureOpenAI.NOT_CONFIGURED, location=location)
            self.logger.debug(self.emoji_safe(msg))
            return None
        
        msg = format_log_message(LogMessages.AzureOpenAI.TRYING_FALLBACK, location=location)
        self.logger.info(self.emoji_safe(msg))
        return self._geocode_with_azure_openai(location)
    
    def get_coordinates_with_fallback(self, location: str) -> Optional[Tuple[float, float]]:
        """
        Get coordinates with fallback strategies for better results
        
        Args:
            location: Location string to geocode
            
        Returns:
            Tuple of (longitude, latitude) or None if not found
        """
        if not location or not location.strip():
            return None
        
        # Try the original location first
        coords = self.get_coordinates(location)
        if coords:
            return coords
        
        # Clean location and try with prefixes removed
        cleaned_location = self._remove_prefixes(location)
        coords = self._try_cleaned_location(location, cleaned_location)
        if coords:
            return coords
        
        # Try comma-separated parts
        coords = self._try_comma_separated_parts(location, cleaned_location)
        if coords:
            return coords
        
        # Try simplified location (common words removed)
        coords = self._try_simplified_location(location)
        if coords:
            return coords
        
        # Try main location (before first comma)
        coords = self._try_main_location(location, cleaned_location)
        if coords:
            return coords
        
        # Try with country suffixes
        coords = self._try_country_suffixes(location, cleaned_location)
        if coords:
            return coords
        
        # Final fallback: Azure OpenAI
        return self._try_azure_openai_fallback(location)


# Global instance
geocoding_service = GeocodingService()

