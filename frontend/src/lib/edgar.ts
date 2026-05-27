// Mirrors backend `REAL_VENDORS[].cik` in capture.py — vendors with SEC EDGAR
// monitoring active. Kept here so VendorCard and DetailPanel can render the
// SEC badge without requiring an API-shape change. If a new EDGAR-eligible
// vendor is added on the backend, add it here too.
const VENDORS_WITH_CIK = new Set(["Snowflake", "Twilio", "AWS"]);

export function isEdgarMonitored(vendorName: string, isDemo: boolean): boolean {
  return !isDemo && VENDORS_WITH_CIK.has(vendorName);
}

export function isSecSourceUrl(url: string | null | undefined): boolean {
  return !!url && url.includes("sec.gov");
}
