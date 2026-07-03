/**
 * Extract a human-readable error message from an Axios error response.
 *
 * Handles common DRF response shapes:
 * - { detail: "..." }
 * - { message: "..." }
 * - { error: "..." }
 * - { field_name: ["error message", ...] } (validation errors)
 */
export function extractErrorMessage(err: unknown, fallback: string): string {
  const data = (err as any)?.response?.data;
  if (!data) return fallback;
  if (typeof data === 'string') return data;
  if (data.detail) return String(data.detail);
  if (data.message) return String(data.message);
  if (data.error) return String(data.error);
  // Validation errors: join first error from each field
  const fieldErrors = Object.values(data)
    .flat()
    .filter((v): v is string => typeof v === 'string');
  if (fieldErrors.length) return fieldErrors.join('; ');
  return fallback;
}
