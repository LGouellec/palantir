package io.palantir.stream.newsmerger;

import org.apache.kafka.common.config.SaslConfigs;
import org.apache.kafka.streams.KafkaStreams;
import org.apache.kafka.streams.StreamsConfig;
import org.apache.kafka.streams.Topology;
import org.apache.kafka.streams.errors.LogAndContinueExceptionHandler;
import org.apache.kafka.streams.errors.StreamsUncaughtExceptionHandler;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import java.io.IOException;
import java.io.Reader;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.EnumMap;
import java.util.Map;
import java.util.Properties;
import java.util.concurrent.CountDownLatch;
import java.util.function.Function;

/**
 * Entry point. Configuration comes from environment variables:
 *
 * <pre>
 * KAFKA_BOOTSTRAP_SERVERS   default localhost:9092
 * KAFKA_CONFIG_PATH         optional properties file (Confluent Cloud creds); both the
 *                           Java client format and the librdkafka format used by the
 *                           other services in this repo (sasl.mechanisms / sasl.username /
 *                           sasl.password) are accepted
 * APPLICATION_ID            default news-merger (consumer group id)
 * OUTPUT_TOPIC              default financial-news
 * INPUT_TOPIC_INVESTING     default investing-news
 * INPUT_TOPIC_SEEKING_ALPHA default seeking-alpha-news
 * INPUT_TOPIC_WSJ           default wsj-articles
 * INPUT_TOPIC_TWITTER       default twitter-tweets
 * PROCESSING_GUARANTEE      default at_least_once (or exactly_once_v2)
 * AUTO_OFFSET_RESET         default earliest
 * NUM_STREAM_THREADS        default 1
 * </pre>
 */
public final class NewsMergerApp {

    private static final Logger LOG = LoggerFactory.getLogger(NewsMergerApp.class);

    private NewsMergerApp() {
    }

    public static void main(String[] args) throws Exception {
        Function<String, String> env = System::getenv;

        Map<NewsSource, String> inputs = inputTopics(env);
        String output = envOr(env, "OUTPUT_TOPIC", "financial-news");
        Properties props = streamsConfig(env);

        Topology topology = NewsMergerTopology.build(inputs, output);
        LOG.info("Starting news-merger: {} -> {}\n{}", inputs.values(), output, topology.describe());

        KafkaStreams streams = new KafkaStreams(topology, props);
        CountDownLatch latch = new CountDownLatch(1);

        streams.setUncaughtExceptionHandler(e -> {
            LOG.error("Stream thread failed, replacing it", e);
            return StreamsUncaughtExceptionHandler.StreamThreadExceptionResponse.REPLACE_THREAD;
        });
        streams.setStateListener((newState, oldState) -> {
            LOG.info("State {} -> {}", oldState, newState);
            if (newState == KafkaStreams.State.ERROR || newState == KafkaStreams.State.NOT_RUNNING) {
                latch.countDown();
            }
        });
        Runtime.getRuntime().addShutdownHook(new Thread(() -> {
            LOG.info("Shutting down news-merger");
            streams.close();
            latch.countDown();
        }, "news-merger-shutdown"));

        streams.start();
        latch.await();
        if (streams.state() == KafkaStreams.State.ERROR) {
            System.exit(1);
        }
    }

    static Map<NewsSource, String> inputTopics(Function<String, String> env) {
        Map<NewsSource, String> inputs = new EnumMap<>(NewsSource.class);
        for (NewsSource source : NewsSource.values()) {
            inputs.put(source, envOr(env, source.topicEnvVar(), source.defaultTopic()));
        }
        return inputs;
    }

    static Properties streamsConfig(Function<String, String> env) throws IOException {
        Properties props = new Properties();
        props.put(StreamsConfig.BOOTSTRAP_SERVERS_CONFIG, envOr(env, "KAFKA_BOOTSTRAP_SERVERS", "localhost:9092"));

        String configPath = env.apply("KAFKA_CONFIG_PATH");
        if (configPath != null && !configPath.isBlank()) {
            props.putAll(loadClientConfig(Path.of(configPath)));
        }

        props.put(StreamsConfig.APPLICATION_ID_CONFIG, envOr(env, "APPLICATION_ID", "news-merger"));
        props.put(StreamsConfig.PROCESSING_GUARANTEE_CONFIG, envOr(env, "PROCESSING_GUARANTEE", StreamsConfig.AT_LEAST_ONCE));
        props.put(StreamsConfig.NUM_STREAM_THREADS_CONFIG, envOr(env, "NUM_STREAM_THREADS", "1"));
        props.put(StreamsConfig.consumerPrefix("auto.offset.reset"), envOr(env, "AUTO_OFFSET_RESET", "earliest"));
        props.put(StreamsConfig.DESERIALIZATION_EXCEPTION_HANDLER_CLASS_CONFIG, LogAndContinueExceptionHandler.class.getName());
        // -1 = broker default (3 on Confluent Cloud). The topology is stateless today, this only
        // matters if a state store / repartition topic is added later.
        props.putIfAbsent(StreamsConfig.REPLICATION_FACTOR_CONFIG, "-1");
        return props;
    }

    /**
     * Loads a client properties file, translating the librdkafka keys used across this
     * repo (kafka_config.properties) into their Java client equivalents.
     */
    static Properties loadClientConfig(Path path) throws IOException {
        Properties raw = new Properties();
        try (Reader reader = Files.newBufferedReader(path)) {
            raw.load(reader);
        }

        Properties props = new Properties();
        String username = null;
        String password = null;
        for (String key : raw.stringPropertyNames()) {
            String value = raw.getProperty(key).trim();
            switch (key) {
                case "sasl.mechanisms" -> props.put(SaslConfigs.SASL_MECHANISM, value);
                case "sasl.username" -> username = value;
                case "sasl.password" -> password = value;
                // librdkafka-only / not meaningful for a Streams app
                case "client.id", "group.id", "session.timeout.ms" -> { }
                default -> props.put(key, value);
            }
        }
        if (username != null && password != null && !props.containsKey(SaslConfigs.SASL_JAAS_CONFIG)) {
            props.put(SaslConfigs.SASL_JAAS_CONFIG, String.format(
                    "org.apache.kafka.common.security.plain.PlainLoginModule required username=\"%s\" password=\"%s\";",
                    username, password));
            props.putIfAbsent(SaslConfigs.SASL_MECHANISM, "PLAIN");
        }
        return props;
    }

    private static String envOr(Function<String, String> env, String name, String fallback) {
        String value = env.apply(name);
        return value == null || value.isBlank() ? fallback : value;
    }
}
