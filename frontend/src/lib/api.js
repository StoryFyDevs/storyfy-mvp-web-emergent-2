/**
 * Safe API utilities for consistent error handling and response parsing
 * Ensures response body is read only once to prevent "body stream already read" errors
 */

// User-friendly error messages mapping
const ERROR_MESSAGES = {
  // Network errors
  'Failed to fetch': 'Network issue detected. Please check your internet connection and try again.',
  'NetworkError': 'Network issue detected. Please check your internet connection and try again.',
  'TypeError: Failed to fetch': 'Unable to connect to the server. Please check your internet connection.',
  
  // Auth errors
  'Token expired': 'Your session has expired. Please log in again.',
  'Unauthorized': 'Your session has expired. Please log in again.',
  'Authentication failed': 'Your session has expired. Please log in again.',
  '401': 'Your session has expired. Please log in again.',
  
  // Credit errors
  'insufficient credits': 'You do not have enough credits for this action.',
  'No audition credits': 'You do not have enough audition credits.',
  'No generation credits': 'You do not have enough generation credits.',
  
  // Rate limiting
  '429': 'Too many requests. Please wait a moment and try again.',
  'Rate limit': 'Too many requests. Please wait a moment and try again.',
  
  // Server errors
  '500': 'Something went wrong on our end. Please try again shortly.',
  '502': 'Service temporarily unavailable. Please try again shortly.',
  '503': 'Service temporarily unavailable. Please try again shortly.',
  
  // Audio/TTS specific
  'Audio generation failed': 'Audio generation service is temporarily unavailable. Please try again shortly.',
  'TTS error': 'Voice generation service is temporarily unavailable. Please try again shortly.',
  'Gemini': 'Voice generation service is temporarily unavailable. Please try again shortly.',
};

/**
 * Maps technical errors to user-friendly messages
 * @param {string} errorMessage - Technical error message
 * @returns {string} User-friendly error message
 */
export function getUserFriendlyError(errorMessage) {
  if (!errorMessage) return 'Something went wrong. Please try again.';
  
  const lowerMessage = errorMessage.toLowerCase();
  
  for (const [key, friendlyMsg] of Object.entries(ERROR_MESSAGES)) {
    if (lowerMessage.includes(key.toLowerCase())) {
      return friendlyMsg;
    }
  }
  
  // Check for status codes
  const statusMatch = errorMessage.match(/\b(4\d{2}|5\d{2})\b/);
  if (statusMatch) {
    const status = statusMatch[1];
    if (status.startsWith('4')) {
      return 'The request could not be processed. Please try again.';
    }
    if (status.startsWith('5')) {
      return 'Service temporarily unavailable. Please try again shortly.';
    }
  }
  
  // If message looks technical (contains stack trace indicators, file paths, etc.)
  if (
    errorMessage.includes('at ') ||
    errorMessage.includes('Error:') ||
    errorMessage.includes('.js:') ||
    errorMessage.includes('undefined') ||
    errorMessage.includes('null') ||
    errorMessage.includes('JSON') ||
    errorMessage.includes('parse') ||
    errorMessage.includes('body stream')
  ) {
    return 'Something went wrong while processing your request. Please try again.';
  }
  
  // Return original if it seems user-friendly (short and doesn't contain technical terms)
  if (errorMessage.length < 100 && !errorMessage.includes('Error')) {
    return errorMessage;
  }
  
  return 'Something went wrong. Please try again.';
}

/**
 * Safe fetch wrapper that handles response parsing correctly
 * Ensures response body is read only once
 * 
 * @param {string} url - The URL to fetch
 * @param {RequestInit} options - Fetch options
 * @returns {Promise<{ok: boolean, data: any, error: string|null, status: number}>}
 */
export async function safeFetch(url, options = {}) {
  try {
    const response = await fetch(url, {
      credentials: 'include',
      ...options,
    });
    
    const status = response.status;
    let data = null;
    let errorMessage = null;
    
    // Try to parse response body as JSON
    const contentType = response.headers.get('content-type') || '';
    
    try {
      if (contentType.includes('application/json')) {
        data = await response.json();
      } else {
        // For non-JSON responses, read as text
        const text = await response.text();
        data = { message: text };
      }
    } catch (parseError) {
      console.error('[safeFetch] Failed to parse response:', parseError);
      data = { message: 'Failed to process server response' };
    }
    
    if (!response.ok) {
      // Extract error message from response data
      errorMessage = data?.detail || data?.message || data?.error || `Request failed with status ${status}`;
      
      return {
        ok: false,
        data: null,
        error: errorMessage,
        status,
      };
    }
    
    return {
      ok: true,
      data,
      error: null,
      status,
    };
  } catch (networkError) {
    console.error('[safeFetch] Network error:', networkError);
    return {
      ok: false,
      data: null,
      error: networkError.message || 'Network error',
      status: 0,
    };
  }
}

/**
 * API call helper with automatic error handling
 * 
 * @param {string} url - The URL to fetch
 * @param {RequestInit} options - Fetch options
 * @param {Object} callbacks - Optional callbacks
 * @param {Function} callbacks.onSuccess - Called with data on success
 * @param {Function} callbacks.onError - Called with user-friendly error on failure
 * @returns {Promise<any>} - Returns data on success, throws on error
 */
export async function apiCall(url, options = {}, callbacks = {}) {
  const token = localStorage.getItem('token') || '';
  
  const result = await safeFetch(url, {
    ...options,
    headers: {
      'Authorization': `Bearer ${token}`,
      ...options.headers,
    },
  });
  
  if (!result.ok) {
    const friendlyError = getUserFriendlyError(result.error);
    
    if (callbacks.onError) {
      callbacks.onError(friendlyError, result.error);
    }
    
    throw new Error(friendlyError);
  }
  
  if (callbacks.onSuccess) {
    callbacks.onSuccess(result.data);
  }
  
  return result.data;
}

/**
 * POST request helper
 */
export async function apiPost(url, body, options = {}) {
  return apiCall(url, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      ...options.headers,
    },
    body: JSON.stringify(body),
    ...options,
  });
}

/**
 * GET request helper
 */
export async function apiGet(url, options = {}) {
  return apiCall(url, {
    method: 'GET',
    ...options,
  });
}

/**
 * PUT request helper
 */
export async function apiPut(url, body, options = {}) {
  return apiCall(url, {
    method: 'PUT',
    headers: {
      'Content-Type': 'application/json',
      ...options.headers,
    },
    body: JSON.stringify(body),
    ...options,
  });
}

/**
 * DELETE request helper
 */
export async function apiDelete(url, options = {}) {
  return apiCall(url, {
    method: 'DELETE',
    ...options,
  });
}

export default {
  safeFetch,
  apiCall,
  apiPost,
  apiGet,
  apiPut,
  apiDelete,
  getUserFriendlyError,
};
