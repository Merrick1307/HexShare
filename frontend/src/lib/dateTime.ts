const ISO_DATE_TIME_WITHOUT_ZONE =
  /^\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}(?::\d{2}(?:\.\d+)?)?$/;

/**
 * Parse API timestamps as instants.
 *
 * Older HexShare database columns store UTC in timestamp-without-time-zone
 * fields, which Pydantic serializes without a trailing offset. Browsers treat
 * those strings as client-local time. Add the UTC marker only for those legacy
 * values; timestamps that already contain Z or an explicit offset are kept.
 */
export function parseApiDate(value: string | number | Date): Date {
  if (value instanceof Date || typeof value === "number") {
    return new Date(value);
  }

  const normalized = value.trim();
  return new Date(
    ISO_DATE_TIME_WITHOUT_ZONE.test(normalized)
      ? `${normalized.replace(" ", "T")}Z`
      : normalized,
  );
}
