package io.palantir.stream.newsmerger;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.apache.kafka.common.serialization.StringDeserializer;
import org.apache.kafka.common.serialization.StringSerializer;
import org.apache.kafka.streams.KeyValue;
import org.apache.kafka.streams.StreamsConfig;
import org.apache.kafka.streams.TestInputTopic;
import org.apache.kafka.streams.TestOutputTopic;
import org.apache.kafka.streams.TopologyTestDriver;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;

import java.util.List;
import java.util.Map;
import java.util.Properties;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

class NewsMergerTopologyTest {

    private static final ObjectMapper MAPPER = new ObjectMapper();

    private TopologyTestDriver driver;
    private Map<NewsSource, TestInputTopic<String, String>> inputs;
    private TestOutputTopic<String, String> output;

    @BeforeEach
    void setUp() {
        Map<NewsSource, String> topics = NewsMergerApp.inputTopics(name -> null);
        Properties props = new Properties();
        props.put(StreamsConfig.APPLICATION_ID_CONFIG, "news-merger-test");
        props.put(StreamsConfig.BOOTSTRAP_SERVERS_CONFIG, "dummy:9092");
        driver = new TopologyTestDriver(NewsMergerTopology.build(topics, "financial-news"), props);

        inputs = new java.util.EnumMap<>(NewsSource.class);
        topics.forEach((source, topic) -> inputs.put(source,
                driver.createInputTopic(topic, new StringSerializer(), new StringSerializer())));
        output = driver.createOutputTopic("financial-news", new StringDeserializer(), new StringDeserializer());
    }

    @AfterEach
    void tearDown() {
        driver.close();
    }

    @Test
    void mapsInvestingNews() throws Exception {
        inputs.get(NewsSource.INVESTING).pipeInput("https://www.investing.com/news/x-123", """
                {"id":"4321","url":"https://www.investing.com/news/x-123","title":"Oil jumps",
                 "author":"Reuters","published_date":"10/01/2025, 09:30 AM","scraped_at":"2025-10-01T13:35:00Z",
                 "word_count":120,"excerpt":"ex","content":"body","category":"Commodities,Energy",
                 "images":["a.png"],"content_md":"# Oil jumps"}
                """);

        KeyValue<String, String> kv = output.readKeyValue();
        JsonNode out = MAPPER.readTree(kv.value);
        assertEquals("4321", kv.key);
        assertEquals("4321", out.get("id").asText());
        assertEquals("Reuters", out.get("author").asText());
        assertEquals("Commodities,Energy", out.get("category").asText());
        assertEquals("body", out.get("content").asText());
        assertEquals("# Oil jumps", out.get("content_md").asText());
        assertEquals("2025-10-01T13:30:00Z", out.get("published_date").asText());
        assertEquals("2025-10-01T13:35:00Z", out.get("scraped_at").asText());
        assertEquals("Oil jumps", out.get("title").asText());
        assertEquals("https://www.investing.com/news/x-123", out.get("url").asText());
        assertEquals("investing", out.get("source").asText());
        // fields not part of the output schema are dropped
        assertFalse(out.has("images"));
        assertFalse(out.has("word_count"));
        assertFalse(out.has("excerpt"));
    }

    @Test
    void mapsSeekingAlphaNews() throws Exception {
        inputs.get(NewsSource.SEEKING_ALPHA).pipeInput(null, """
                {"url":"https://seekingalpha.com/news/4499123-apple-beats","title":"Apple beats",
                 "author":"SA News","published_date":"2025-10-01T09:30:00-04:00","scraped_at":"2025-10-01T13:31:00.123Z",
                 "word_count":80,"excerpt":"","content":"c","category":"market-news","content_md":"md"}
                """);

        KeyValue<String, String> kv = output.readKeyValue();
        JsonNode out = MAPPER.readTree(kv.value);
        assertEquals("4499123", kv.key);
        assertEquals("market-news", out.get("category").asText());
        assertEquals("2025-10-01T13:30:00Z", out.get("published_date").asText());
        assertEquals("2025-10-01T13:31:00.123Z", out.get("scraped_at").asText());
        assertEquals("seeking-alpha", out.get("source").asText());
    }

    @Test
    void mapsWsjArticles() throws Exception {
        inputs.get(NewsSource.WSJ).pipeInput("k", """
                {"url":"https://www.wsj.com/finance/stocks/fed-holds-rates-1a2b3c4d?mod=hp","title":"Fed holds",
                 "author":"Nick T","published_date":"2025-10-01T18:00:00.000Z","scraped_at":"2025-10-01T18:05:00Z",
                 "word_count":900,"excerpt":"e","content":"c","base_url":"https://www.wsj.com","content_md":"md"}
                """);

        KeyValue<String, String> kv = output.readKeyValue();
        JsonNode out = MAPPER.readTree(kv.value);
        assertEquals("1a2b3c4d", kv.key);
        assertEquals("finance", out.get("category").asText());
        assertEquals("Nick T", out.get("author").asText());
        assertEquals("2025-10-01T18:00:00Z", out.get("published_date").asText());
        assertFalse(out.has("base_url"));
        assertEquals("wsj", out.get("source").asText());
    }

    @Test
    void mapsTweets() throws Exception {
        inputs.get(NewsSource.TWITTER).pipeInput("elonmusk", """
                {"id":"1840000000000000000","conversationId":"1","userId":"44196397","username":"elonmusk",
                 "name":"Elon Musk","text":"Tesla deliveries up","html":"<p/>",
                 "permanentUrl":"https://x.com/elonmusk/status/1840000000000000000","timestamp":1759325400,
                 "timeIso":"2025-10-01T13:30:00.000Z","likes":1,"retweets":2,"replies":3,"bookmarkCount":4,
                 "hashtags":[],"mentions":[],"urls":[],"photos":[],"videos":[],"isRetweet":false,"isReply":false,
                 "isQuoted":false,"source":"$TSLA","scrapedAt":"2025-10-01T13:40:00.000Z","content_md":"md"}
                """);

        KeyValue<String, String> kv = output.readKeyValue();
        JsonNode out = MAPPER.readTree(kv.value);
        assertEquals("1840000000000000000", kv.key);
        assertEquals("elonmusk", out.get("author").asText());
        assertEquals("$TSLA", out.get("category").asText());
        assertEquals("Tesla deliveries up", out.get("content").asText());
        assertEquals("", out.get("title").asText());
        assertEquals("https://x.com/elonmusk/status/1840000000000000000", out.get("url").asText());
        assertEquals("2025-10-01T13:30:00Z", out.get("published_date").asText());
        assertFalse(out.has("likes"));
        // "source" is the origin of the record, not the tweet's search query (which goes to category)
        assertEquals("twitter", out.get("source").asText());
    }

    @Test
    void tweetFallsBackToEpochSecondsTimestamp() throws Exception {
        inputs.get(NewsSource.TWITTER).pipeInput("u", """
                {"id":"1","username":"u","text":"t","permanentUrl":"https://x.com/u/status/1","timestamp":1759325400}
                """);
        assertEquals("2025-10-01T13:30:00Z", MAPPER.readTree(output.readValue()).get("published_date").asText());
    }

    @Test
    void mergesAllSourcesIntoOneTopic() {
        inputs.get(NewsSource.INVESTING).pipeInput("a", "{\"id\":\"1\",\"url\":\"u1\"}");
        inputs.get(NewsSource.SEEKING_ALPHA).pipeInput("b", "{\"url\":\"https://seekingalpha.com/news/2-x\"}");
        inputs.get(NewsSource.WSJ).pipeInput("c", "{\"url\":\"https://www.wsj.com/tech/x-deadbeef\"}");
        inputs.get(NewsSource.TWITTER).pipeInput("d", "{\"id\":\"4\",\"permanentUrl\":\"u4\"}");

        List<String> keys = output.readKeyValuesToList().stream().map(kv -> kv.key).toList();
        assertEquals(List.of("1", "2", "deadbeef", "4"), keys);
    }

    @Test
    void dropsMalformedAndIdLessRecordsWithoutStopping() {
        inputs.get(NewsSource.INVESTING).pipeInput("a", "not json");
        inputs.get(NewsSource.INVESTING).pipeInput("a", "[1,2]");
        inputs.get(NewsSource.INVESTING).pipeInput("a", (String) null);
        inputs.get(NewsSource.WSJ).pipeInput("a", "{\"title\":\"no url\"}");
        inputs.get(NewsSource.INVESTING).pipeInput("a", "{\"id\":\"ok\"}");

        List<KeyValue<String, String>> out = output.readKeyValuesToList();
        assertEquals(1, out.size());
        assertEquals("ok", out.get(0).key);
        assertTrue(output.isEmpty());
    }

    @Test
    void idFallsBackToUrlWhenPatternDoesNotMatch() {
        inputs.get(NewsSource.SEEKING_ALPHA).pipeInput("a", "{\"url\":\"https://seekingalpha.com/article/abc\"}");
        assertEquals("https://seekingalpha.com/article/abc", output.readKeyValue().key);
    }
}
