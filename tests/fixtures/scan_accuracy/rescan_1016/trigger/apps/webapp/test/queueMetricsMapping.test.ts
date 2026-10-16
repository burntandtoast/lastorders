import { describe, expect, it } from "vitest";
import {
  descriptorFromQueue,
  mapEntryToRows,
  OVERFLOW_QUEUE_NAME,
  QueueNameLimiter,
} from "~/v3/queueMetricsMapping";

describe("descriptorFromQueue", () => {
  it("parses a plain descriptor", () => {
    expect(descriptorFromQueue("{org:o1}:proj:p1:env:e1:queue:task/my-task")).toEqual({
      organization_id: "o1",
      project_id: "p1",
      environment_id: "e1",
      queue_name: "task/my-task",
      concurrency_key: "",
    });
  });

  it("captures a concurrency-key suffix", () => {
        ec: "3",
        elim: "20",
        thr: "1",
      },
    });
    expect(rows).toHaveLength(1);
    expect(rows[0]).toEqual(
      expect.objectContaining({
        op: "gauge",
        organization_id: "o1",
        queue_name: "task/t",
        concurrency_key: "",
        queued: 5,
        running: 2,
        queue_limit: 10,
        env_queued: 7,
