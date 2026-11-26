package io.palantir.stream.newsmerger;

import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.apache.kafka.common.serialization.Serdes;
import org.apache.kafka.streams.KeyValue;
import org.apache.kafka.streams.StreamsBuilder;
import org.apache.kafka.streams.Topology;
import org.apache.kafka.streams.kstream.Consumed;
import org.apache.kafka.streams.kstream.KStream;
import org.apache.kafka.streams.kstream.Named;
import org.apache.kafka.streams.kstream.Produced;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import java.util.List;
import java.util.Map;

/**
 * investing-news ─┐
 * seeking-alpha ──┤ map to FinancialNews ─► merge ─► financial-news (key = id)
 * wsj-articles ───┤
 * twitter-tweets ─┘
 *
 * Stateless: no state stores or repartition topics, records are re-keyed by their
 * article id on the way out. Malformed or id-less records are logged and dropped.
 */
public final class NewsMergerTopology {

    private static final Logger LOG = LoggerFactory.getLogger(NewsMergerTopology.class);
    private static final ObjectMapper MAPPER = new ObjectMapper();

    private NewsMergerTopology() {
    }

    public static Topology build(Map<NewsSource, String> inputTopics, String outputTopic) {
        StreamsBuilder builder = new StreamsBuilder();

        KStream<String, String> merged = null;
        for (Map.Entry<NewsSource, String> entry : inputTopics.entrySet()) {
            NewsSource source = entry.getKey();
            String topic = entry.getValue();
            String name = source.name().toLowerCase().replace('_', '-');

            KStream<String, String> mapped = builder
                    .stream(topic, Consumed.with(Serdes.String(), Serdes.String()).withName("source-" + name))
                    .flatMap((key, value) -> convert(source, topic, value), Named.as("map-" + name));

            merged = merged == null ? mapped : merged.merge(mapped, Named.as("merge-" + name));
        }

        if (merged == null) {
            throw new IllegalArgumentException("At least one input topic is required");
        }
        merged.to(outputTopic, Produced.with(Serdes.String(), Serdes.String()).withName("sink-financial-news"));
        return builder.build();
    }

    static List<KeyValue<String, String>> convert(NewsSource source, String topic, String value) {
        if (value == null || value.isBlank()) {
            return List.of(); // tombstone / empty payload
        }
        try {
            JsonNode node = MAPPER.readTree(value);
            if (node == null || !node.isObject()) {
                LOG.warn("Skipping non-object record from {}", topic);
                return List.of();
            }
            FinancialNews news = source.map(node);
            if (news.id() == null || news.id().isBlank()) {
                LOG.warn("Skipping record from {} without id/url", topic);
                return List.of();
            }
            return List.of(KeyValue.pair(news.id(), MAPPER.writeValueAsString(news)));
        } catch (JsonProcessingException e) {
            LOG.warn("Skipping malformed JSON from {}: {}", topic, e.getOriginalMessage());
            return List.of();
        }
    }
}
