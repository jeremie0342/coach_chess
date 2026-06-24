"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { api } from "@/lib/api";
import type { EnqueueResponse, JobStatus } from "@/types/jobs";

type JobState = {
  jobId: string | null;
  status: string | null;
  isRunning: boolean;
  isComplete: boolean;
  isFailed: boolean;
  result: unknown | null;
  error: string | null;
};

const TERMINAL = new Set(["complete", "JobStatus.complete", "failed", "JobStatus.not_found", "not_found"]);

export function useAsyncJob<TBody = Record<string, unknown>>(enqueuePath: string) {
  const [state, setState] = useState<JobState>({
    jobId: null, status: null, isRunning: false,
    isComplete: false, isFailed: false, result: null, error: null,
  });
  const timer = useRef<number | null>(null);

  const clearTimer = () => {
    if (timer.current != null) { window.clearTimeout(timer.current); timer.current = null; }
  };

  useEffect(() => () => clearTimer(), []);

  const poll = useCallback(async (jobId: string) => {
    try {
      const s = await api<JobStatus>(`/jobs/${jobId}`);
      const term = TERMINAL.has(s.status);
      setState((prev) => ({
        ...prev,
        status: s.status,
        result: s.result,
        isRunning: !term,
        isComplete: term && s.success !== false && s.status.includes("complete"),
        isFailed: term && (s.success === false || s.status.includes("not_found") || s.status.includes("failed")),
      }));
      if (!term) {
        timer.current = window.setTimeout(() => poll(jobId), 1500);
      }
    } catch (e) {
      setState((prev) => ({ ...prev, error: String(e), isRunning: false, isFailed: true }));
    }
  }, []);

  const start = useCallback(async (body?: TBody) => {
    clearTimer();
    setState({
      jobId: null, status: "queued", isRunning: true,
      isComplete: false, isFailed: false, result: null, error: null,
    });
    try {
      const r = await api<EnqueueResponse>(enqueuePath, { json: body ?? {} });
      setState((prev) => ({ ...prev, jobId: r.job_id, status: "queued" }));
      poll(r.job_id);
    } catch (e) {
      setState((prev) => ({ ...prev, error: String(e), isRunning: false, isFailed: true }));
    }
  }, [enqueuePath, poll]);

  const reset = useCallback(() => {
    clearTimer();
    setState({ jobId: null, status: null, isRunning: false, isComplete: false, isFailed: false, result: null, error: null });
  }, []);

  return { ...state, start, reset };
}
