export function extractErrorMessage(err: unknown, fallback: string): string {
  const detail = (err as { response?: { data?: { detail?: string } } })?.response
    ?.data?.detail;
  if (detail) return detail;
  if (err instanceof Error) return err.message;
  return fallback;
}
