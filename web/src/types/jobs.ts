export type EnqueueResponse = {
  job_id: string;
  queued_at: string;
  function: string;
};

export type JobStatus = {
  job_id: string;
  status: string; // queued | deferred | in_progress | complete | not_found
  function: string | null;
  enqueue_time: string | null;
  start_time: string | null;
  finish_time: string | null;
  result: unknown | null;
  success: boolean | null;
};
