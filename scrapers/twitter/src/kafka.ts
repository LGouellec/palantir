import { Kafka, Partitioners, type Producer, logLevel } from "kafkajs";
import { parseKafkaProperties, type AppConfig } from "./config.js";
import { log } from "./logger.js";

/**
 * Thin wrapper around a kafkajs producer.
 *
 * Connection settings come from a Confluent-style properties file
 * (KAFKA_CONFIG_FILE) when provided — supporting SASL_SSL / PLAIN against
 * Confluent Cloud — and fall back to a plaintext broker (e.g. the local
 * `kafka:29092` from docker-compose) otherwise. KAFKA_BOOTSTRAP_SERVERS
 * always overrides the brokers from the file.
 */
export class KafkaSink {
  private producer: Producer | null = null;
  private connected = false;

  constructor(private readonly cfg: AppConfig) {}

  private buildKafka(): Kafka {
    const props = this.cfg.kafkaConfigFile
      ? parseKafkaProperties(this.cfg.kafkaConfigFile)
      : {};

    const brokersStr =
      this.cfg.kafkaBootstrapServers ??
      props["bootstrap.servers"] ??
      "localhost:9092";
    const brokers = brokersStr.split(",").map((b) => b.trim());

    const usesSsl =
      (props["security.protocol"] ?? "").toUpperCase().includes("SSL");
    const saslUser = props["sasl.username"];
    const saslPass = props["sasl.password"];

    log.info(`Kafka brokers: ${brokers.join(", ")} (ssl=${usesSsl})`);

    return new Kafka({
      clientId: props["client.id"] ?? "twitter-scraper",
      brokers,
      ssl: usesSsl,
      sasl:
        saslUser && saslPass
          ? {
              mechanism: "plain",
              username: saslUser,
              password: saslPass,
            }
          : undefined,
      logLevel: logLevel.ERROR,
    });
  }

  async connect(): Promise<void> {
    if (this.connected) return;
    const kafka = this.buildKafka();
    this.producer = kafka.producer({
      createPartitioner: Partitioners.DefaultPartitioner,
      allowAutoTopicCreation: true,
    });
    await this.producer.connect();
    this.connected = true;
    log.ok(`Connected to Kafka, producing to topic "${this.cfg.kafkaTopic}"`);
  }

  /** Produce one record, keyed so tweets from the same author co-locate. */
  async send(key: string, value: unknown): Promise<void> {
    if (!this.producer) throw new Error("KafkaSink not connected");
    await this.producer.send({
      topic: this.cfg.kafkaTopic,
      messages: [{ key, value: JSON.stringify(value) }],
    });
  }

  async disconnect(): Promise<void> {
    if (this.producer && this.connected) {
      await this.producer.disconnect();
      this.connected = false;
      log.info("Disconnected from Kafka");
    }
  }
}
