/**
 * Kappa interpretation utilities.
 *
 * Single source of truth for Cohen's Kappa threshold values
 * and their corresponding interpretations, colour classes, and badge variants.
 */

export function getKappaInterpretation(kappa: number | null): string {
  if (kappa === null || kappa === undefined) return 'Not Available';

  if (kappa < 0.20) return 'Slight Agreement';
  if (kappa < 0.40) return 'Fair Agreement';
  if (kappa < 0.60) return 'Moderate Agreement';
  if (kappa < 0.80) return 'Substantial Agreement';
  return 'Almost Perfect';
}

export function getKappaColorClass(kappa: number | null): string {
  if (kappa === null || kappa === undefined) return 'text-muted-foreground';

  if (kappa < 0.40) return 'text-[color:var(--color-error)]';
  if (kappa < 0.70) return 'text-[color:var(--color-warning)]';
  return 'text-[color:var(--color-success)]';
}

export function getKappaBadgeVariant(kappa: number | null): 'default' | 'secondary' | 'destructive' | 'outline' {
  if (kappa === null || kappa === undefined) return 'secondary';

  if (kappa < 0.40) return 'destructive';
  if (kappa < 0.70) return 'secondary';
  return 'default';
}

export function formatKappa(kappa: number | null): string {
  if (kappa === null || kappa === undefined) return 'N/A';
  return kappa.toFixed(3);
}
