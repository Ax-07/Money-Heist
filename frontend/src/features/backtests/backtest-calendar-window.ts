import type { DatasetPreview, SplitIndices } from "@/lib/api/schemas";
import {
  PRESET_MIN_TEST_BARS,
  splitWindow60_20_20,
} from "./backtest-config";

export const CAMPAIGN_DURATION_MONTHS = [1, 3, 6, 9, 12] as const;
export type CampaignDurationMonths = (typeof CAMPAIGN_DURATION_MONTHS)[number];

export type CalendarWindowBounds = {
  minStartDate: string;
  maxStartDate: string;
  coverageStartDate: string;
  coverageEndExclusiveDate: string;
};

export type CalendarWindowPlan = {
  startDate: string;
  endExclusiveDate: string;
  startIndex: number;
  endIndex: number;
  warmupBars: number;
  windowBars: number;
  effectiveStartAt: string;
  effectiveEndAt: string;
  split: SplitIndices;
};

type DateParts = {
  year: number;
  month: number;
  day: number;
};

function parseDateParts(value: string): DateParts {
  const match = /^(\d{4})-(\d{2})-(\d{2})$/.exec(value);
  if (!match) {
    throw new Error("La date de début doit être au format YYYY-MM-DD.");
  }
  const year = Number(match[1]);
  const month = Number(match[2]);
  const day = Number(match[3]);
  const timestamp = Date.UTC(year, month - 1, day);
  const parsed = new Date(timestamp);
  if (
    parsed.getUTCFullYear() !== year ||
    parsed.getUTCMonth() !== month - 1 ||
    parsed.getUTCDate() !== day
  ) {
    throw new Error("La date de début n'est pas une date calendaire valide.");
  }
  return { year, month, day };
}

function formatDate(year: number, month: number, day: number): string {
  return [
    String(year).padStart(4, "0"),
    String(month).padStart(2, "0"),
    String(day).padStart(2, "0"),
  ].join("-");
}

function dateToUtcMs(value: string): number {
  const parts = parseDateParts(value);
  return Date.UTC(parts.year, parts.month - 1, parts.day);
}

export function addCalendarMonthsDate(value: string, months: number): string {
  if (!Number.isInteger(months)) {
    throw new Error("Le décalage calendaire doit être un nombre entier de mois.");
  }
  const source = parseDateParts(value);
  const absoluteMonth = source.year * 12 + (source.month - 1) + months;
  const targetYear = Math.floor(absoluteMonth / 12);
  const targetMonthZeroBased = absoluteMonth - targetYear * 12;
  const lastDay = new Date(
    Date.UTC(targetYear, targetMonthZeroBased + 1, 0),
  ).getUTCDate();
  return formatDate(
    targetYear,
    targetMonthZeroBased + 1,
    Math.min(source.day, lastDay),
  );
}

function formatUtcDate(timestamp: number): string {
  return new Date(timestamp).toISOString().slice(0, 10);
}

function upperBound(values: readonly number[], target: number): number {
  let low = 0;
  let high = values.length;
  while (low < high) {
    const middle = Math.floor((low + high) / 2);
    if (values[middle]! <= target) low = middle + 1;
    else high = middle;
  }
  return low;
}

function datasetCoverage(preview: DatasetPreview): {
  axis: number[];
  intervalMs: number;
  startMs: number;
  endExclusiveMs: number;
} {
  const axis = preview.candle_close_ms.map(Number);
  if (axis.length !== preview.candle_count || axis.length < PRESET_MIN_TEST_BARS) {
    throw new Error(
      "Le dataset ne fournit pas un axe temporel complet pour sélectionner une fenêtre datée.",
    );
  }
  for (let index = 1; index < axis.length; index += 1) {
    if (!Number.isFinite(axis[index]) || axis[index]! <= axis[index - 1]!) {
      throw new Error("L'axe temporel du dataset doit être strictement croissant.");
    }
  }
  const intervalMs = axis[1]! - axis[0]!;
  if (!Number.isFinite(intervalMs) || intervalMs <= 0) {
    throw new Error("Impossible de déduire l'intervalle du dataset.");
  }
  return {
    axis,
    intervalMs,
    startMs: axis[0]! - intervalMs,
    endExclusiveMs: axis[axis.length - 1]!,
  };
}

function validateDurationMonths(durationMonths: number): void {
  if (!Number.isInteger(durationMonths) || durationMonths <= 0) {
    throw new Error("La durée de campagne doit être un nombre entier de mois > 0.");
  }
}

export function calendarWindowBounds(
  preview: DatasetPreview,
  durationMonths: number,
): CalendarWindowBounds {
  validateDurationMonths(durationMonths);
  const coverage = datasetCoverage(preview);
  const coverageStartDate = formatUtcDate(coverage.startMs);
  const coverageEndExclusiveDate = formatUtcDate(coverage.endExclusiveMs);
  const maxStartDate = addCalendarMonthsDate(
    coverageEndExclusiveDate,
    -durationMonths,
  );
  if (maxStartDate < coverageStartDate) {
    throw new Error(
      `Le dataset est trop court pour une fenêtre de ${durationMonths} mois calendaires.`,
    );
  }
  return {
    minStartDate: coverageStartDate,
    maxStartDate,
    coverageStartDate,
    coverageEndExclusiveDate,
  };
}

export function calendarWindowPlan(
  preview: DatasetPreview,
  startDate: string,
  durationMonths: number,
): CalendarWindowPlan {
  const bounds = calendarWindowBounds(preview, durationMonths);
  if (startDate < bounds.minStartDate || startDate > bounds.maxStartDate) {
    throw new Error(
      `Début hors couverture : choisir une date entre ${bounds.minStartDate} ` +
        `et ${bounds.maxStartDate} pour ${durationMonths} mois.`,
    );
  }

  const coverage = datasetCoverage(preview);
  const startMs = dateToUtcMs(startDate);
  const endExclusiveDate = addCalendarMonthsDate(startDate, durationMonths);
  const endExclusiveMs = dateToUtcMs(endExclusiveDate);

  if (endExclusiveMs > coverage.endExclusiveMs) {
    throw new Error(
      `La fenêtre ${startDate} → ${endExclusiveDate} dépasse la couverture du dataset.`,
    );
  }

  // candle_close_ms est un axe de clôtures :
  // - au début, on exclut la candle qui clôture exactement à startDate ;
  // - à la fin exclusive, on inclut la candle qui clôture exactement à endExclusiveDate.
  const startIndex = upperBound(coverage.axis, startMs);
  const endExclusiveIndex = upperBound(coverage.axis, endExclusiveMs);
  const endIndex = endExclusiveIndex - 1;
  if (
    startIndex >= coverage.axis.length ||
    endIndex < startIndex ||
    endIndex >= coverage.axis.length
  ) {
    throw new Error("La fenêtre calendaire ne contient pas assez de bougies dans ce dataset.");
  }

  const windowBars = endIndex - startIndex + 1;
  if (windowBars < PRESET_MIN_TEST_BARS) {
    throw new Error(
      `La fenêtre doit contenir au moins ${PRESET_MIN_TEST_BARS} bougies.`,
    );
  }

  return {
    startDate,
    endExclusiveDate,
    startIndex,
    endIndex,
    warmupBars: startIndex,
    windowBars,
    effectiveStartAt: new Date(coverage.axis[startIndex]!).toISOString(),
    effectiveEndAt: new Date(coverage.axis[endIndex]!).toISOString(),
    split: splitWindow60_20_20(startIndex, endIndex),
  };
}
