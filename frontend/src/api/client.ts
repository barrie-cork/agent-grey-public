/**
 * Axios API Client for Django Backend
 *
 * Handles:
 * - CSRF token management (Django requirement)
 * - Session cookie authentication
 * - Error interceptors
 * - Organisation context validation
 */

import axios, { type AxiosError, type AxiosInstance, type AxiosResponse } from 'axios';

/**
 * Get CSRF token from cookie
 * Django sets this token in the csrftoken cookie
 */
function getCsrfToken(): string | null {
  const name = 'csrftoken';
  let cookieValue: string | null = null;

  if (document.cookie && document.cookie !== '') {
    const cookies = document.cookie.split(';');
    for (let i = 0; i < cookies.length; i++) {
      const cookie = cookies[i]?.trim();
      if (cookie && cookie.substring(0, name.length + 1) === (name + '=')) {
        cookieValue = decodeURIComponent(cookie.substring(name.length + 1));
        break;
      }
    }
  }

  return cookieValue;
}

/**
 * Get CSRF token from meta tag (alternative method)
 * Django template should include: <meta name="csrf-token" content="{{ csrf_token }}">
 */
function getCsrfTokenFromMeta(): string | null {
  const metaTag = document.querySelector('meta[name="csrf-token"]');
  return metaTag ? metaTag.getAttribute('content') : null;
}

/**
 * Create configured Axios instance
 */
const apiClient: AxiosInstance = axios.create({
  baseURL: '/api/',
  withCredentials: true,  // CRITICAL: Include session cookies
  headers: {
    'Content-Type': 'application/json',
    'X-Requested-With': 'XMLHttpRequest',
  },
  timeout: 30000,  // 30 second timeout
});

/**
 * Request interceptor: Add CSRF token to all requests
 */
apiClient.interceptors.request.use(
  (config): any => {
    // Get CSRF token from cookie or meta tag
    const csrfToken = getCsrfToken() || getCsrfTokenFromMeta();

    if (csrfToken && config.headers) {
      config.headers['X-CSRFToken'] = csrfToken;
    }

    return config;
  },
  (error: AxiosError): any => {
    return Promise.reject(error);
  }
);

/**
 * Response interceptor: Handle common errors
 */
apiClient.interceptors.response.use(
  (response: AxiosResponse) => {
    return response;
  },
  (error: AxiosError) => {
    if (error.response) {
      const { status, data } = error.response;

      // Handle specific error cases
      switch (status) {
        case 401:
          // Unauthorized - redirect to login
          console.error('Unauthorized: Redirecting to login');
          window.location.href = '/accounts/login/';
          break;

        case 403:
          // Forbidden - might be missing organisation context
          if ((data as any)?.error === 'no_organisation') {
            console.error('No organisation context');
            window.location.href = '/organisation/select/';
          } else if ((data as any)?.error === 'not_member') {
            console.error('Not a member of this organisation');
            // Show error toast or redirect
          }
          break;

        case 404:
          // Not found
          console.error('Resource not found:', error.config?.url);
          break;

        case 409:
          // Conflict (e.g., already decided, already resolved)
          console.warn('Conflict:', (data as any)?.message);
          break;

        case 500:
          // Server error
          console.error('Server error:', (data as any)?.message);
          break;
      }
    } else if (error.request) {
      // Request made but no response received
      console.error('Network error: No response received');
    } else {
      // Error in request setup
      console.error('Request error:', error.message);
    }

    return Promise.reject(error);
  }
);

export default apiClient;

/**
 * API Response Types (matching Django serializers)
 */

export interface ApiError {
  error: string;
  message: string;
}

export interface PaginatedResponse<T> {
  count: number;
  next: string | null;
  previous: string | null;
  page: number;
  num_pages: number;
  results: T[];
}
