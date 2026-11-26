package io.palantir.stream.newsmerger;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNull;

class DateNormalizerTest {

    @Test
    void isoInstantIsKeptInUtc() {
        assertEquals("2025-10-01T13:30:00Z", DateNormalizer.normalize("2025-10-01T13:30:00.000Z"));
    }

    @Test
    void isoWithOffsetIsConvertedToUtc() {
        assertEquals("2025-10-01T13:30:00Z", DateNormalizer.normalize("2025-10-01T09:30:00-04:00"));
    }

    @Test
    void localIsoIsInterpretedAsUsEastern() {
        // EDT in summer (UTC-4), EST in winter (UTC-5)
        assertEquals("2025-07-01T13:30:00Z", DateNormalizer.normalize("2025-07-01T09:30:00"));
        assertEquals("2025-01-15T14:30:00Z", DateNormalizer.normalize("2025-01-15T09:30:00"));
    }

    @Test
    void investingFormat() {
        assertEquals("2025-10-01T17:05:00Z", DateNormalizer.normalize("10/01/2025, 01:05 PM"));
        assertEquals("2025-10-01T17:05:00Z", DateNormalizer.normalize("10/01/2025, 01:05 pm"));
    }

    @Test
    void unparseableValuesPassThrough() {
        assertEquals("2 hours ago", DateNormalizer.normalize("2 hours ago"));
        assertEquals("", DateNormalizer.normalize(""));
        assertNull(DateNormalizer.normalize(null));
    }
}
