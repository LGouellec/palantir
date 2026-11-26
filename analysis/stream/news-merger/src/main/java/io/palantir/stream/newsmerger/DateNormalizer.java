package io.palantir.stream.newsmerger;

import java.time.Instant;
import java.time.LocalDateTime;
import java.time.OffsetDateTime;
import java.time.ZoneId;
import java.time.format.DateTimeFormatter;
import java.time.format.DateTimeFormatterBuilder;
import java.time.format.DateTimeParseException;
import java.util.List;
import java.util.Locale;

/**
 * Normalizes the heterogeneous date strings produced by the scrapers into a single
 * ISO-8601 UTC representation (e.g. {@code 2025-10-01T13:30:00Z}).
 *
 * <ul>
 *   <li>wsj / twitter: {@code 2025-10-01T13:30:00.000Z}</li>
 *   <li>seeking-alpha: {@code 2025-10-01T09:30:00-04:00} (or without offset)</li>
 *   <li>investing: {@code 10/01/2025, 09:30 AM}</li>
 * </ul>
 *
 * Strings without an explicit offset are interpreted in US Eastern time (where the
 * scraped sites publish). Unparseable values are passed through unchanged so no
 * information is lost.
 */
public final class DateNormalizer {

    static final ZoneId MARKET_ZONE = ZoneId.of("America/New_York");

    private static final List<DateTimeFormatter> LOCAL_FORMATS = List.of(
            DateTimeFormatter.ISO_LOCAL_DATE_TIME,
            new DateTimeFormatterBuilder()
                    .parseCaseInsensitive()
                    .appendPattern("MM/dd/yyyy, hh:mm a")
                    .toFormatter(Locale.US),
            new DateTimeFormatterBuilder()
                    .parseCaseInsensitive()
                    .appendPattern("M/d/yyyy, h:mm a")
                    .toFormatter(Locale.US),
            DateTimeFormatter.ofPattern("yyyy-MM-dd HH:mm:ss", Locale.US));

    private DateNormalizer() {
    }

    public static String normalize(String raw) {
        if (raw == null) {
            return null;
        }
        String value = raw.trim();
        if (value.isEmpty()) {
            return raw;
        }
        try {
            return OffsetDateTime.parse(value, DateTimeFormatter.ISO_OFFSET_DATE_TIME).toInstant().toString();
        } catch (DateTimeParseException ignored) {
            // try next
        }
        for (DateTimeFormatter format : LOCAL_FORMATS) {
            try {
                return LocalDateTime.parse(value, format).atZone(MARKET_ZONE).toInstant().toString();
            } catch (DateTimeParseException ignored) {
                // try next
            }
        }
        return raw;
    }

    /** Epoch seconds (twitter {@code timestamp}) to ISO-8601 UTC. */
    public static String fromEpochSeconds(long epochSeconds) {
        return Instant.ofEpochSecond(epochSeconds).toString();
    }
}
